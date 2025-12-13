(function () {
  function scorePassword(pw, username) {
    if (!pw) return { score: 0, label: "" };

    var score = 0;
    var hasLower = /[a-z]/.test(pw);
    var hasUpper = /[A-Z]/.test(pw);
    var hasDigit = /\d/.test(pw);
    var hasSpecial = /[^A-Za-z0-9]/.test(pw);

    if (pw.length >= 12) score += 2;
    if (pw.length >= 16) score += 1;
    if (hasLower) score += 1;
    if (hasUpper) score += 1;
    if (hasDigit) score += 1;
    if (hasSpecial) score += 1;

    if (/\s/.test(pw)) score -= 2;
    if (username && pw.toLowerCase().includes(username.toLowerCase())) score -= 2;

    if (!hasSpecial) return { score: Math.min(score, 3), label: score <= 1 ? "Very weak" : score <= 3 ? "Weak" : "Good" };

    if (score <= 1) return { score: 1, label: "Very weak" };
    if (score <= 3) return { score: 2, label: "Weak" };
    if (score <= 5) return { score: 3, label: "Good" };
    return { score: 4, label: "Strong" };
  }

  function updateMeter() {
    var pw = document.getElementById("password");
    var un = document.getElementById("username");
    var bar = document.querySelector("[data-meter-bar]");
    var text = document.querySelector("[data-meter-text]");

    if (!pw || !bar || !text) return;

    var res = scorePassword(pw.value, un ? un.value : "");

    var widths = { 0: "0%", 1: "25%", 2: "45%", 3: "70%", 4: "100%" };
    var colors = { 0: "#ff4d4d", 1: "#ff4d4d", 2: "#ff9f43", 3: "#2ecc71", 4: "#16a34a" };

    bar.style.width = widths[res.score] || "0%";
    bar.style.background = colors[res.score] || "#ff4d4d";
    text.textContent = "Password strength: " + (res.label || "");
  }

  document.addEventListener("input", function (e) {
    if (e.target && (e.target.id === "password" || e.target.id === "username")) {
      updateMeter();
    }
  });

  document.addEventListener("DOMContentLoaded", updateMeter);
})();
