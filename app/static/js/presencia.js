(() => {
    const url = document.body.dataset.presenciaUrl;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
    if (!url || !csrf) return;

    let enviando = false;

    async function enviarPulso() {
        if (enviando || document.visibilityState !== "visible") return;
        enviando = true;
        try {
            await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    ruta: window.location.pathname,
                    pagina: document.title,
                }),
            });
        } catch (_error) {
            // La presencia nunca debe interrumpir el uso normal de SICODE.
        } finally {
            enviando = false;
        }
    }

    window.setTimeout(enviarPulso, 400);
    window.setInterval(enviarPulso, 20000);

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") enviarPulso();
    });
})();
