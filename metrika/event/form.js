const form = document.querySelector("form");
const status = document.querySelector('[role="status"]');

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error("Заявка не принята");
    const result = await response.json();
    status.textContent = `Заявка ${result.id} принята`;
  } catch (error) {
    status.textContent = error.message;
  }
});
