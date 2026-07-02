/**
 * Cloudflare Worker — мост между Telegram и GitHub Actions.
 *
 * Telegram шлёт сюда вебхуком каждое новое сообщение боту, мгновенно
 * (без опроса). Если текст сообщения похож на команду проверки,
 * воркер сразу дёргает GitHub Actions (workflow_dispatch на
 * instant_respond.yml) с chat_id этого пользователя — дальше уже
 * GitHub сам всё проверяет и присылает ответ в Telegram.
 *
 * Как задеплоить и настроить — см. university_tracker/webhook/README.md.
 */

const TRIGGER_TEXTS = ["/start", "/check", "/status", "/report", "проверить"];

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    // Telegram присылает секрет, заданный при регистрации вебхука
    // (setWebhook?...&secret_token=...) — так посторонние не смогут
    // дёргать этот адрес и тратить твои GitHub Actions минуты.
    const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (!env.WEBHOOK_SECRET || secret !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch (err) {
      return new Response("bad request", { status: 400 });
    }

    const message = update.message;
    const text = ((message && message.text) || "").trim().toLowerCase();
    const chatId = message && message.chat && message.chat.id;

    const triggered = TRIGGER_TEXTS.some((t) => text.includes(t));

    if (triggered && chatId) {
      const url =
        `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}` +
        `/actions/workflows/instant_respond.yml/dispatches`;

      const ghResponse = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "admission-tracker-webhook",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { chat_id: String(chatId) },
        }),
      });

      if (!ghResponse.ok) {
        const body = await ghResponse.text();
        console.log("GitHub dispatch failed:", ghResponse.status, body);
      }
    }

    // Telegram ждёт быстрый ответ 200 на сам вебхук — реальный ответ
    // пользователю придёт отдельно, из GitHub Actions, через 1-2 минуты.
    return new Response("OK", { status: 200 });
  },
};
