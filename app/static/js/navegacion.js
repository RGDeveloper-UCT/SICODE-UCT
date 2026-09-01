(() => {
    const dropdowns = Array.from(document.querySelectorAll('[data-nav-dropdown]'));
    if (!dropdowns.length) return;

    const cerrar = (dropdown, devolverFoco = false) => {
        const boton = dropdown.querySelector('[data-nav-toggle]');
        dropdown.classList.remove('is-open');
        if (boton) {
            boton.setAttribute('aria-expanded', 'false');
            if (devolverFoco) boton.focus();
        }
    };

    const cerrarTodos = (excepto = null) => {
        dropdowns.forEach((dropdown) => {
            if (dropdown !== excepto) cerrar(dropdown);
        });
    };

    dropdowns.forEach((dropdown) => {
        const boton = dropdown.querySelector('[data-nav-toggle]');
        const panel = dropdown.querySelector('[data-nav-panel]');
        if (!boton || !panel) return;

        boton.addEventListener('click', (evento) => {
            evento.stopPropagation();
            const abrir = !dropdown.classList.contains('is-open');
            cerrarTodos(dropdown);
            dropdown.classList.toggle('is-open', abrir);
            boton.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        });

        boton.addEventListener('keydown', (evento) => {
            if (evento.key !== 'ArrowDown') return;
            evento.preventDefault();
            cerrarTodos(dropdown);
            dropdown.classList.add('is-open');
            boton.setAttribute('aria-expanded', 'true');
            const primerControl = panel.querySelector('a[href], button:not([disabled])');
            if (primerControl) primerControl.focus();
        });

        panel.addEventListener('click', (evento) => {
            if (evento.target.closest('a[href]')) cerrar(dropdown);
        });
    });

    document.addEventListener('click', (evento) => {
        const dentro = dropdowns.some((dropdown) => dropdown.contains(evento.target));
        if (!dentro) cerrarTodos();
    });

    document.addEventListener('keydown', (evento) => {
        if (evento.key !== 'Escape') return;
        const abierto = dropdowns.find((dropdown) => dropdown.classList.contains('is-open'));
        if (abierto) cerrar(abierto, true);
    });

    window.addEventListener('resize', () => cerrarTodos(), { passive: true });

    const favoritosRoot = document.querySelector('[data-favoritos-root]');
    if (!favoritosRoot) return;

    const api = favoritosRoot.dataset.favoritosApi;
    const lista = favoritosRoot.querySelector('[data-favoritos-lista]');
    const contador = favoritosRoot.querySelector('[data-favoritos-contador]');
    const badge = favoritosRoot.querySelector('[data-favoritos-badge]');
    const botonAgregar = favoritosRoot.querySelector('[data-favorito-agregar]');
    const aviso = favoritosRoot.querySelector('[data-favoritos-aviso]');
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const iconosValidos = new Set([
        'grid', 'search', 'folder', 'payment', 'coordination', 'shield', 'ai',
        'loan', 'alert', 'log', 'nexo', 'online', 'users', 'system', 'account', 'star'
    ]);
    const urlActual = `${window.location.pathname}${window.location.search}`;
    let estado = { favoritos: [], total: 0, maximo: 6 };

    const tituloPaginaActual = () => {
        const candidato = document.querySelector('main h1, main .titulo-principal, main h2');
        const visible = candidato?.textContent?.replace(/\s+/g, ' ').trim();
        if (visible) return visible.slice(0, 160);
        const titulo = (document.title || 'SICODE-UCT')
            .replace(/\s*[|·-]\s*SICODE(?:-UCT)?\s*$/i, '')
            .trim();
        return (titulo || 'Acceso SICODE').slice(0, 160);
    };

    const svgIcono = (nombre) => {
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        const use = document.createElementNS(ns, 'use');
        const icono = iconosValidos.has(nombre) ? nombre : 'star';
        svg.setAttribute('aria-hidden', 'true');
        use.setAttribute('href', `#nav-icon-${icono}`);
        svg.appendChild(use);
        return svg;
    };

    const mostrarAviso = (texto = '', tipo = '') => {
        if (!aviso) return;
        aviso.textContent = texto;
        aviso.className = `favoritos-aviso${tipo ? ` favoritos-aviso--${tipo}` : ''}`;
    };

    const actualizarBotonAgregar = () => {
        if (!botonAgregar) return;
        const texto = botonAgregar.querySelector('span');
        const yaExiste = estado.favoritos.some((item) => item.url === urlActual);
        if (yaExiste) {
            botonAgregar.disabled = true;
            if (texto) texto.textContent = 'Ya está en favoritos';
            return;
        }
        if (estado.total >= estado.maximo) {
            botonAgregar.disabled = true;
            if (texto) texto.textContent = `Límite ${estado.maximo}/${estado.maximo}`;
            return;
        }
        botonAgregar.disabled = false;
        if (texto) texto.textContent = 'Agregar página actual';
    };

    const renderFavoritos = (datos) => {
        estado = {
            favoritos: Array.isArray(datos?.favoritos) ? datos.favoritos : [],
            total: Number(datos?.total || 0),
            maximo: Number(datos?.maximo || 6),
        };

        if (contador) contador.textContent = `${estado.total}/${estado.maximo}`;
        if (badge) badge.textContent = `${estado.total} de ${estado.maximo}`;
        if (!lista) return;
        lista.replaceChildren();

        if (!estado.favoritos.length) {
            const vacio = document.createElement('div');
            vacio.className = 'favoritos-vacio';
            vacio.innerHTML = '<strong>Aún no tiene favoritos.</strong><span>Abra una pantalla de SICODE y use “Agregar página actual”.</span>';
            lista.appendChild(vacio);
            actualizarBotonAgregar();
            return;
        }

        estado.favoritos.forEach((favorito) => {
            const fila = document.createElement('div');
            fila.className = 'favorito-item';

            const enlace = document.createElement('a');
            enlace.className = 'favorito-enlace';
            enlace.href = favorito.url;
            enlace.title = favorito.titulo;

            const icono = document.createElement('span');
            icono.className = 'favorito-icono';
            icono.appendChild(svgIcono(favorito.icono));

            const texto = document.createElement('span');
            texto.className = 'favorito-texto';
            const fuerte = document.createElement('strong');
            fuerte.textContent = favorito.titulo;
            const ruta = document.createElement('small');
            ruta.textContent = favorito.url;
            texto.append(fuerte, ruta);
            enlace.append(icono, texto);

            const quitar = document.createElement('button');
            quitar.className = 'favorito-quitar';
            quitar.type = 'button';
            quitar.dataset.favoritoEliminar = String(favorito.id);
            quitar.setAttribute('aria-label', `Quitar ${favorito.titulo} de favoritos`);
            quitar.title = 'Quitar de favoritos';
            quitar.textContent = '×';

            fila.append(enlace, quitar);
            lista.appendChild(fila);
        });

        actualizarBotonAgregar();
    };

    const cargarFavoritos = async () => {
        if (!api) return;
        try {
            const respuesta = await fetch(api, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            if (!respuesta.ok) throw new Error('No se pudieron cargar los favoritos.');
            const datos = await respuesta.json();
            renderFavoritos(datos);
            mostrarAviso();
        } catch (error) {
            if (lista) {
                const fallo = document.createElement('div');
                fallo.className = 'favoritos-vacio favoritos-vacio--error';
                fallo.textContent = 'No fue posible cargar sus favoritos.';
                lista.replaceChildren(fallo);
            }
            mostrarAviso(error.message || 'Error al cargar favoritos.', 'error');
        }
    };

    botonAgregar?.addEventListener('click', async () => {
        if (!api || botonAgregar.disabled) return;
        botonAgregar.disabled = true;
        mostrarAviso('Guardando acceso…');
        try {
            const respuesta = await fetch(api, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf,
                },
                body: JSON.stringify({ titulo: tituloPaginaActual(), url: urlActual }),
            });
            const datos = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(datos.error || 'No fue posible guardar el favorito.');
            await cargarFavoritos();
            mostrarAviso(datos.ya_existia ? 'Esta página ya estaba guardada.' : 'Favorito agregado correctamente.', 'ok');
        } catch (error) {
            mostrarAviso(error.message || 'No fue posible guardar el favorito.', 'error');
            actualizarBotonAgregar();
        }
    });

    lista?.addEventListener('click', async (evento) => {
        const boton = evento.target.closest('[data-favorito-eliminar]');
        if (!boton || !api) return;
        evento.preventDefault();
        evento.stopPropagation();
        boton.disabled = true;
        mostrarAviso('Quitando favorito…');
        try {
            const respuesta = await fetch(`${api}${boton.dataset.favoritoEliminar}`, {
                method: 'DELETE',
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/json',
                    'X-CSRFToken': csrf,
                },
            });
            const datos = await respuesta.json().catch(() => ({}));
            if (!respuesta.ok) throw new Error(datos.error || 'No fue posible quitar el favorito.');
            await cargarFavoritos();
            mostrarAviso('Favorito eliminado.', 'ok');
        } catch (error) {
            boton.disabled = false;
            mostrarAviso(error.message || 'No fue posible quitar el favorito.', 'error');
        }
    });

    cargarFavoritos();
})();
