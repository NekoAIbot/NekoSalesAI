/* ================================================================
   auth.js — Unified authentication for Nera web apps.
   
   Token storage strategy:
   - localStorage: "neko_token" — persists across tabs/browser restarts
   - sessionStorage: "nekosales.desk.token" — used by desk.js
   
   Both are written on login so the desk and other pages can find the token.
   ================================================================ */

(function () {
  "use strict";

  var TOKEN_KEY_LOCAL = "neko_token";
  var TOKEN_KEY_SESSION = "nekosales.desk.token";

  function storeToken(token) {
    localStorage.setItem(TOKEN_KEY_LOCAL, token);
    sessionStorage.setItem(TOKEN_KEY_SESSION, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY_LOCAL);
    sessionStorage.removeItem(TOKEN_KEY_SESSION);
  }

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY_SESSION) || localStorage.getItem(TOKEN_KEY_LOCAL);
  }

  // ---- Login form handler ----
  function initLoginForm() {
    var form = document.getElementById("login-form");
    if (!form) return;

    var email = document.getElementById("login-email");
    var password = document.getElementById("login-password");
    var totpField = document.getElementById("totp-field");
    var totpInput = document.getElementById("login-totp");
    var recoveryField = document.getElementById("recovery-field");
    var useRecovery = document.getElementById("use-recovery");
    var error = document.getElementById("login-error");
    var totpRequired = false;
    var useRecoveryCode = false;

    if (useRecovery) {
      useRecovery.addEventListener("click", function (e) {
        e.preventDefault();
        useRecoveryCode = !useRecoveryCode;
        if (useRecoveryCode) {
          totpInput.setAttribute("placeholder", "Recovery code");
          totpInput.setAttribute("pattern", "");
          totpInput.style.letterSpacing = "0.1em";
          useRecovery.textContent = "Use authenticator code instead";
        } else {
          totpInput.removeAttribute("placeholder");
          totpInput.setAttribute("pattern", "[0-9]{6}");
          totpInput.style.letterSpacing = "0.3em";
          useRecovery.textContent = "Use a recovery code instead";
        }
      });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      error.classList.add("hidden");

      var body = { email: email.value, password: password.value };
      var endpoint = "/api/v1/auth/login";

      if (totpRequired) {
        endpoint = useRecoveryCode ? "/api/v1/auth/login/recovery-code" : "/api/v1/auth/login/totp";
        body[useRecoveryCode ? "recovery_code" : "totp_code"] = totpInput.value;
      }

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.access_token) {
          storeToken(data.access_token);
          // Redirect to desk or the page we came from
          var params = new URLSearchParams(window.location.search);
          var next = params.get("next") || "/dashboard";
          window.location.href = next;
        } else if (data.detail && data.detail.includes("TOTP code required")) {
          totpRequired = true;
          totpField.classList.remove("hidden");
          recoveryField.classList.remove("hidden");
        } else {
          error.textContent = data.detail || "Invalid email or password.";
          error.classList.remove("hidden");
        }
      })
      .catch(function () {
        error.textContent = "Could not reach the server. Try again.";
        error.classList.remove("hidden");
      });
    });
  }

  // ---- Signup form handler ----
  function initSignupForm() {
    var form = document.getElementById("signup-form");
    if (!form) return;

    var password = document.getElementById("signup-password");
    var confirm = document.getElementById("signup-confirm");
    var toggle = document.getElementById("toggle-password");
    var error = document.getElementById("signup-error");
    var matchMsg = document.getElementById("match-msg");

    var checks = {
      length: document.getElementById("check-length"),
      upper: document.getElementById("check-upper"),
      lower: document.getElementById("check-lower"),
      digit: document.getElementById("check-digit")
    };

    function updateChecks() {
      var val = password.value;
      checks.length.style.color = val.length >= 8 ? "var(--signal-live)" : "var(--ink-4)";
      checks.upper.style.color = /[A-Z]/.test(val) ? "var(--signal-live)" : "var(--ink-4)";
      checks.lower.style.color = /[a-z]/.test(val) ? "var(--signal-live)" : "var(--ink-4)";
      checks.digit.style.color = /[0-9]/.test(val) ? "var(--signal-live)" : "var(--ink-4)";
    }

    password.addEventListener("input", updateChecks);

    if (toggle) {
      toggle.addEventListener("click", function () {
        password.type = password.type === "password" ? "text" : "password";
      });
    }

    confirm.addEventListener("input", function () {
      if (confirm.value && confirm.value !== password.value) {
        matchMsg.textContent = "Passwords do not match";
        matchMsg.style.color = "#8b2e2a";
      } else if (confirm.value) {
        matchMsg.textContent = "Passwords match";
        matchMsg.style.color = "var(--signal-live)";
      } else {
        matchMsg.textContent = "";
      }
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      error.classList.add("hidden");

      if (password.value !== confirm.value) {
        error.textContent = "Passwords do not match.";
        error.classList.remove("hidden");
        return;
      }

      var fullName = document.getElementById("signup-fullname");
      var company = document.getElementById("signup-company");

      fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("signup-email").value,
          password: password.value,
          full_name: fullName ? fullName.value : "",
          company_name: company ? company.value : "",
        }),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.id) {
          // Registration successful — redirect to login
          window.location.href = "/login?registered=true";
        } else if (data.detail) {
          error.textContent = data.detail;
          error.classList.remove("hidden");
        }
      })
      .catch(function () {
        error.textContent = "Could not reach the server. Try again.";
        error.classList.remove("hidden");
      });
    });
  }

  // ---- Forgot password form handler ----
  function initForgotPasswordForm() {
    var form = document.getElementById("forgot-form");
    if (!form) return;

    var successMsg = document.getElementById("forgot-success");
    var error = document.getElementById("forgot-error");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      error.classList.add("hidden");

      fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("forgot-email").value,
        }),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.message) {
          successMsg.classList.remove("hidden");
          form.classList.add("hidden");
        } else if (data.detail) {
          error.textContent = data.detail;
          error.classList.remove("hidden");
        }
      })
      .catch(function () {
        error.textContent = "Could not reach the server. Try again.";
        error.classList.remove("hidden");
      });
    });
  }

  // ---- Reset password form handler ----
  function initResetPasswordForm() {
    var form = document.getElementById("reset-form");
    if (!form) return;

    var successMsg = document.getElementById("reset-success");
    var error = document.getElementById("reset-error");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      error.classList.add("hidden");

      var token = document.getElementById("reset-token").value;
      var password = document.getElementById("reset-password").value;
      var confirm = document.getElementById("reset-confirm").value;

      if (password !== confirm) {
        error.textContent = "Passwords do not match.";
        error.classList.remove("hidden");
        return;
      }

      fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: token,
          new_password: password,
        }),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.message) {
          successMsg.classList.remove("hidden");
          form.classList.add("hidden");
          // Redirect to login after 2 seconds
          setTimeout(function () {
            window.location.href = "/login?reset=true";
          }, 2000);
        } else if (data.detail) {
          error.textContent = data.detail;
          error.classList.remove("hidden");
        }
      })
      .catch(function () {
        error.textContent = "Could not reach the server. Try again.";
        error.classList.remove("hidden");
      });
    });
  }

  // ---- Email verification handler ----
  function initEmailVerification() {
    var form = document.getElementById("verify-form");
    if (!form) return;

    var successMsg = document.getElementById("verify-success");
    var error = document.getElementById("verify-error");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      error.classList.add("hidden");

      fetch("/api/v1/auth/email-verification/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("verify-email").value,
          code: document.getElementById("verify-code").value,
        }),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.message) {
          successMsg.classList.remove("hidden");
          form.classList.add("hidden");
          // Redirect to login after 2 seconds
          setTimeout(function () {
            window.location.href = "/login?verified=true";
          }, 2000);
        } else if (data.detail) {
          error.textContent = data.detail;
          error.classList.remove("hidden");
        }
      })
      .catch(function () {
        error.textContent = "Could not reach the server. Try again.";
        error.classList.remove("hidden");
      });
    });
  }

  // ---- Auto-redirect if already logged in ----
  function checkExistingSession() {
    var token = getToken();
    if (!token) return;

    // If we're on login/signup/forgot/reset pages and have a token,
    // verify it's still valid by fetching /auth/me
    var path = window.location.pathname;
    if (path === "/login" || path === "/signup" || path === "/forgot-password" || path === "/reset-password") {
      fetch("/api/v1/auth/me", {
        headers: { "Authorization": "Bearer " + token },
      })
      .then(function (r) {
        if (r.ok) {
          window.location.href = "/dashboard";
        }
      })
      .catch(function () {});
    }
  }

  // ---- Init on DOM ready ----
  function init() {
    initLoginForm();
    initSignupForm();
    initForgotPasswordForm();
    initResetPasswordForm();
    initEmailVerification();
    checkExistingSession();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
