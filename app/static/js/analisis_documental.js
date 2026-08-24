(() => {
    const input = document.querySelector('[data-pdf-input]');
    const nombre = document.querySelector('[data-pdf-name]');
    if (input && nombre) {
        input.addEventListener('change', () => {
            const archivo = input.files && input.files[0];
            nombre.textContent = archivo ? archivo.name : 'Ningún archivo seleccionado';
        });
    }

    const formularioAnalisis = document.querySelector('[data-analisis-form]');
    const loader = document.querySelector('[data-analisis-loader]');
    if (formularioAnalisis && loader) {
        formularioAnalisis.addEventListener('submit', () => {
            loader.hidden = false;
        });
    }

    const selectorTipo = document.querySelector('[data-tipo-registro]');
    const paneles = Array.from(document.querySelectorAll('[data-tipo-panel]'));

    const actualizarPaneles = () => {
        if (!selectorTipo) return;
        const tipo = selectorTipo.value;
        paneles.forEach((panel) => {
            const tipos = (panel.dataset.tipoPanel || '').split(/\s+/).filter(Boolean);
            const visible = tipos.includes(tipo);
            panel.hidden = !visible;
            panel.querySelectorAll('input, select, textarea').forEach((campo) => {
                if (campo.dataset.requiredOriginal === '1') {
                    campo.required = visible;
                }
            });
        });
    };

    paneles.forEach((panel) => {
        panel.querySelectorAll('[required]').forEach((campo) => {
            campo.dataset.requiredOriginal = '1';
        });
    });

    if (selectorTipo) {
        selectorTipo.addEventListener('change', actualizarPaneles);
        actualizarPaneles();
    }
})();
