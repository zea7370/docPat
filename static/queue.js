Flask==3.0.3
pandas==2.2.2
function startQueuePolling(doctorId, targetSelector) {
  if (!doctorId) return;
  const target = document.querySelector(targetSelector);
  async function fetchQueue() {
    try {
      const res = await fetch(`/api/queue/${doctorId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (!target) return;
      if (!data.queue || data.queue.length === 0) {
        target.innerHTML = "<p>No queue for today.</p>";
        return;
      }
      const ol = document.createElement('ol');
      data.queue.forEach(item => {
        const li = document.createElement('li');
        li.textContent = `${item.Name} (${item.Patient_ID}) — Position ${item.Queue_Position}`;
        ol.appendChild(li);
      });
      target.innerHTML = '';
      target.appendChild(ol);
    } catch (e) {
      console.error("queue fetch error", e);
    }
  }
  fetchQueue();
  // poll every 10 seconds
  setInterval(fetchQueue, 10000);
}
function toggleTheme() {
    document.body.classList.toggle('theme-dark');
}