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
            const primerEnlace = panel.querySelector('a[href]');
            if (primerEnlace) primerEnlace.focus();
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
})();
