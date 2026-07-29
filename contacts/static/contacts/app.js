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
            fetch("/api/weather/?city=" + encodeURIComponent(city))
                .then(function (resp) {
                    if (!resp.ok) throw new Error("weather unavailable");
                    return resp.json();
                })
                .then(function (data) {
                    var text = Math.round(data.temperature) + "°C, " + data.humidity + "% hum, " + data.windspeed + " km/h wind";
                    cells.forEach(function (cell) { cell.textContent = text; });
                })
                .catch(function () {
                    cells.forEach(function (cell) { cell.textContent = "—"; });
                });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initFormValidation();
        initSortSubmit();
        initWeather();
    });
})();
