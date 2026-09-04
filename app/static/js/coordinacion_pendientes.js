document.addEventListener("DOMContentLoaded", () => {
    const monto = document.querySelector('input[name="total"]');
    if (monto) {
        monto.setAttribute("step", "0.01");
        monto.setAttribute("min", "0");
    }

    const tarjetas = Array.from(document.querySelectorAll(".resumen-coordinacion-inicio .tarjeta.indicador"));
    const tarjeta = tarjetas.find((item) => {
        const titulo = item.querySelector("h2");
        return titulo && titulo.textContent.trim().toLowerCase() === "información pendiente";
    });

    if (!tarjeta) return;

    const abrir = () => {
        window.location.assign("/coordinacion/pendientes");
    };

    tarjeta.setAttribute("role", "link");
    tarjeta.setAttribute("tabindex", "0");
    tarjeta.setAttribute("aria-label", "Abrir bandeja de información pendiente de Coordinación");
    tarjeta.style.cursor = "pointer";
    tarjeta.title = "Abrir bandeja de verificación";

    tarjeta.addEventListener("click", abrir);
    tarjeta.addEventListener("keydown", (evento) => {
        if (evento.key === "Enter" || evento.key === " ") {
            evento.preventDefault();
            abrir();
        }
    });
});
