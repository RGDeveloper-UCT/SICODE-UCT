(() => {
    const panel = document.getElementById("uo-panel");
    if (!panel) return;

    const url = panel.dataset.datosUrl;
    const cuerpo = document.getElementById("uo-cuerpo");
    const totalUsuarios = document.getElementById("uo-total-usuarios");
    const totalSesiones = document.getElementById("uo-total-sesiones");
    const actualizado = document.getElementById("uo-actualizado");
    const filtro = document.getElementById("uo-filtro");
    const recargar = document.getElementById("uo-recargar");
    const vacio = document.getElementById("uo-vacio");
    const error = document.getElementById("uo-error");

    let usuarios = [];
    let consultando = false;

    function formatearFecha(valor) {
        const fecha = new Date(valor);
        if (Number.isNaN(fecha.getTime())) return "—";
        return fecha.toLocaleString("es-GT", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    function textoActividad(segundos) {
        const n = Number(segundos || 0);
        if (n < 8) return "Ahora";
        if (n < 60) return `Hace ${n} s`;
        const minutos = Math.floor(n / 60);
        return `Hace ${minutos} min`;
    }

    function celda(texto, clase) {
        const td = document.createElement("td");
        if (clase) td.className = clase;
        td.textContent = texto;
        return td;
    }

    function renderizar() {
        const termino = (filtro.value || "").trim().toLowerCase();
        const visibles = usuarios.filter((item) => {
            if (!termino) return true;
            return [item.nombre, item.usuario, item.rol, item.pagina, item.ruta]
                .filter(Boolean)
                .some((valor) => String(valor).toLowerCase().includes(termino));
        });

        cuerpo.replaceChildren();
        vacio.hidden = visibles.length !== 0;

        for (const item of visibles) {
            const tr = document.createElement("tr");

            const estado = document.createElement("td");
            const insignia = document.createElement("span");
            insignia.className = "uo-estado-online";
            const punto = document.createElement("span");
            punto.className = "uo-punto";
            punto.setAttribute("aria-hidden", "true");
            const texto = document.createElement("span");
            texto.textContent = "Online";
            insignia.append(punto, texto);
            estado.appendChild(insignia);
            tr.appendChild(estado);

            const usuario = document.createElement("td");
            const nombre = document.createElement("strong");
            nombre.textContent = item.nombre;
            const cuenta = document.createElement("small");
            cuenta.textContent = `@${item.usuario}`;
            usuario.append(nombre, cuenta);
            tr.appendChild(usuario);

            tr.appendChild(celda(item.rol));

            const pagina = document.createElement("td");
            const paginaNombre = document.createElement("strong");
            paginaNombre.textContent = item.pagina || "SICODE";
            const ruta = document.createElement("small");
            ruta.textContent = item.ruta || "/";
            pagina.append(paginaNombre, ruta);
            tr.appendChild(pagina);

            tr.appendChild(celda(formatearFecha(item.iniciado_en), "uo-fecha"));
            tr.appendChild(celda(textoActividad(item.segundos_desde_pulso), "uo-actividad"));

            const sesiones = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = "uo-sesiones";
            badge.textContent = String(item.sesiones);
            sesiones.appendChild(badge);
            tr.appendChild(sesiones);

            cuerpo.appendChild(tr);
        }
    }

    async function actualizar() {
        if (consultando) return;
        consultando = true;
        recargar.disabled = true;
        try {
            const respuesta = await fetch(url, {
                credentials: "same-origin",
                cache: "no-store",
                headers: {"Accept": "application/json"},
            });
            if (!respuesta.ok) throw new Error("Respuesta no válida");
            const datos = await respuesta.json();
            usuarios = Array.isArray(datos.usuarios) ? datos.usuarios : [];
            totalUsuarios.textContent = String(datos.total_usuarios ?? usuarios.length);
            totalSesiones.textContent = String(datos.total_sesiones ?? 0);
            actualizado.textContent = new Date().toLocaleTimeString("es-GT", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            });
            error.hidden = true;
            renderizar();
        } catch (_err) {
            error.hidden = false;
        } finally {
            consultando = false;
            recargar.disabled = false;
        }
    }

    filtro.addEventListener("input", renderizar);
    recargar.addEventListener("click", actualizar);

    actualizar();
    window.setInterval(actualizar, 10000);
})();
