(function () {
    "use strict";

    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    // Deliberately looser than the server, which parses with libphonenumber.
    // Client-side validation is here to catch typos early, not to be the
    // authority — being stricter than the backend would reject numbers the
    // API accepts, which is the worse failure.
    var PHONE_SEPARATORS = /[\s\-()]/g;
    var PHONE_RE = /^\+?\d{7,15}$/;

    function feedbackFor(field) {
        return field.parentElement.querySelector(".invalid-feedback");
    }

    function setInvalid(field, message) {
        field.classList.add("is-invalid");
        var feedback = feedbackFor(field);
        if (feedback) feedback.textContent = message;
    }

    function setValid(field) {
        field.classList.remove("is-invalid");
        // Clear d-block too, or a server-rendered error (e.g. "phone already
        // exists") stays on screen after the user has corrected the field.
        var feedback = feedbackFor(field);
        if (feedback) feedback.classList.remove("d-block");
    }

    function validateField(field) {
        if (field.name === "email") {
            if (!EMAIL_RE.test(field.value.trim())) {
                setInvalid(field, "Enter a valid email address.");
                return false;
            }
        } else if (field.name === "phone") {
            var digits = field.value.trim().replace(PHONE_SEPARATORS, "");
            if (!PHONE_RE.test(digits)) {
                setInvalid(field, "Enter a valid phone number, e.g. 123 456 789.");
                return false;
            }
        }
        setValid(field);
        return true;
    }

    function initFormValidation() {
        var form = document.getElementById("contact-form");
        if (!form) return;

        var fields = form.querySelectorAll("#id_email, #id_phone");
        fields.forEach(function (field) {
            field.addEventListener("blur", function () { validateField(field); });
        });

        form.addEventListener("submit", function (e) {
            var valid = true;
            fields.forEach(function (field) {
                if (!validateField(field)) valid = false;
            });
            if (!valid) e.preventDefault();
        });
    }

    function initSortSubmit() {
        var select = document.getElementById("sort-select");
        if (select) select.addEventListener("change", function () { select.form.submit(); });
    }

    // Nominatim returns the full administrative chain, e.g. "Londo, Yabanguia,
    // Gothèye, Tillabéri, Niger". Town plus country is enough to spot a wrong
    // match without turning the cell into a paragraph.
    function shortenLocation(displayName) {
        if (!displayName) return "";
        var parts = displayName.split(",").map(function (p) { return p.trim(); });
        if (parts.length < 2) return parts[0] || "";
        return parts[0] + ", " + parts[parts.length - 1];
    }

    function initWeather() {
        var rows = document.querySelectorAll("tr[data-city]");
        if (!rows.length) return;

        // Dedupe by city so a 25-row page with repeated cities fires one
        // fetch per distinct city instead of one per row.
        var cities = new Set();
        rows.forEach(function (row) {
            var city = row.dataset.city;
            if (city) cities.add(city);
        });

        cities.forEach(function (city) {
            var cells = document.querySelectorAll('tr[data-city="' + CSS.escape(city) + '"] .weather-cell');

            // Second line names the place actually matched. Shown inline rather
            // than as a title tooltip: a near-miss like "Londo" for "London"
            // returns real weather for Niger, and the user only discovers that
            // if they can see it without knowing to hover.
            function render(text, subtitle, cssClass) {
                cells.forEach(function (cell) {
                    cell.textContent = "";

                    var main = document.createElement("div");
                    main.textContent = text;
                    if (cssClass) main.classList.add(cssClass);
                    cell.appendChild(main);

                    if (subtitle) {
                        var note = document.createElement("div");
                        note.className = "small text-muted";
                        note.textContent = subtitle;
                        cell.appendChild(note);
                    }
                });
            }

            fetch("/api/weather/?city=" + encodeURIComponent(city))
                .then(function (resp) {
                    if (resp.ok) return resp.json();
                    // 404 means the city itself is wrong, which the user can fix.
                    // Anything else is our problem, not theirs — say so plainly
                    // rather than implying they mistyped.
                    if (resp.status === 404) {
                        render("Unknown city", "Check the spelling.", "text-danger");
                    } else {
                        render("—", "Weather service unavailable.", "text-muted");
                    }
                    return null;
                })
                .then(function (data) {
                    if (!data) return;
                    render(
                        Math.round(data.temperature) + "°C, " + data.humidity + "% hum, " + data.windspeed + " km/h wind",
                        shortenLocation(data.location)
                    );
                })
                .catch(function () {
                    // Network error reaching our own server.
                    render("—", "Could not load weather.", "text-muted");
                });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initFormValidation();
        initSortSubmit();
        initWeather();
    });
})();
