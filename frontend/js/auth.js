// Login and registration pages.
(function () {
  const errorBox = document.getElementById("error");
  const submit = document.getElementById("submit");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }
  function clearError() { errorBox.classList.add("hidden"); errorBox.textContent = ""; }
  document.querySelectorAll("input").forEach((el) => el.addEventListener("input", clearError));

  // Already logged in? Go straight to the chat.
  if (getToken()) {
    fetch("/api/me", { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((res) => { if (res.ok) window.location.replace("/index.html"); else clearLogin(); })
      .catch(() => clearLogin());
  }

  async function login(email, password) {
    const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    saveLogin(data.token, data.user);
    window.location.replace("/index.html");
  }

  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;
      if (!email || !password) { showError("Enter your email and password."); return; }
      submit.disabled = true;
      try { await login(email, password); }
      catch (e) { showError(e.message); }
      finally { submit.disabled = false; }
    });
  }

  const registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const name = document.getElementById("name").value.trim();
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;
      const confirm = document.getElementById("confirm").value;
      if (!name || !email || !password) { showError("Fill in every field."); return; }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { showError("Enter a valid email address."); return; }
      if (password.length < 8) { showError("The password must have at least 8 characters."); return; }
      if (password !== confirm) { showError("The passwords do not match."); return; }
      submit.disabled = true;
      try {
        await api("/api/auth/register", { method: "POST", body: JSON.stringify({ name, email, password }) });
        await login(email, password);
      } catch (e) {
        showError(e.message);
      } finally {
        submit.disabled = false;
      }
    });
  }
})();
