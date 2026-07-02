# Мгновенный ответ бота через Cloudflare Worker

По умолчанию бот отвечает через GitHub Actions за 1-5 минут (а иногда и
дольше — расписание GitHub у этого аккаунта тикает нечасто). Чтобы ответ
приходил почти мгновенно, Telegram может слать сообщения не через опрос
(`getUpdates`), а вебхуком — напрямую на сервер, который сразу же
запускает проверку в GitHub Actions. GitHub Actions сам постоянным
сервером быть не может, поэтому нужен маленький бесплатный посредник —
Cloudflare Worker (`worker.js` в этой папке).

Всё бесплатно, ничего постоянно не платится.

## Шаг 1. Создать токен GitHub

1. Открой https://github.com/settings/personal-access-tokens/new
2. **Token name**: любое, например `admission-tracker-webhook`.
3. **Expiration**: на своё усмотрение (можно "No expiration" или подальше
   в будущее — тогда не придётся пересоздавать).
4. **Repository access** → **Only select repositories** → выбери
   `Claymie/snake-game-python`.
5. **Permissions** → **Repository permissions** → **Actions** →
   **Read and write**. Остальное можно не трогать.
6. **Generate token**, скопируй значение (начинается с `github_pat_...`)
   — оно понадобится в шаге 3 и больше нигде не покажется.

## Шаг 2. Завести Cloudflare Worker

1. Зарегистрируйся на https://dash.cloudflare.com/sign-up (просто почта
   и пароль, карта не нужна).
2. В боковом меню — **Workers & Pages** → **Create** →
   **Create Worker**.
3. Дай любое имя (например `admission-tracker-webhook`) → **Deploy**
   (создастся заготовка "Hello World").
4. Нажми **Edit code**.
5. Удали весь код-заготовку и вставь вместо него содержимое файла
   `worker.js` из этой папки (скопируй его целиком).
6. **Save and deploy**.
7. Сверху страницы будет ссылка вида
   `https://admission-tracker-webhook.<твой-поддомен>.workers.dev` —
   это и есть адрес твоего вебхука, он понадобится в шаге 4.

## Шаг 3. Задать переменные воркера

В настройках воркера: **Settings → Variables and Secrets → Add**.

Добавь четыре переменные:

| Имя             | Значение                              | Тип     |
|-----------------|----------------------------------------|---------|
| `GH_OWNER`      | `Claymie`                              | Text    |
| `GH_REPO`       | `snake-game-python`                    | Text    |
| `GITHUB_TOKEN`  | токен из шага 1 (`github_pat_...`)     | **Secret** |
| `WEBHOOK_SECRET`| любая случайная строка (придумай сам, например `a8f3k29dQz71x`) | **Secret** |

Для `GITHUB_TOKEN` и `WEBHOOK_SECRET` обязательно выбери тип **Secret**
(encrypt), не Text — иначе значение будет видно всем, у кого есть доступ
к настройкам воркера.

`WEBHOOK_SECRET` — просто придуманная тобой строка, она нигде заранее не
существует, ты её сам генерируешь (любые буквы/цифры, подлиннее). Она
понадобится ещё раз в шаге 4 — должна совпадать один в один.

Сохрани.

## Шаг 4. Подключить вебхук в Telegram

Открой в браузере (замени `<TOKEN>` на токен бота, `<WORKER_URL>` — на
ссылку из шага 2.7, `<SECRET>` — на строку из шага 3, ту же самую):

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<SECRET>
```

Должно вернуться `{"ok":true,"result":true,"description":"Webhook was set"}`.

## Проверка

Напиши боту `/start` (или нажми кнопку "Проверить статус") — ответ должен
прийти за 1-2 минуты вместо ожидания расписания. Если не пришло — открой
в Cloudflare **Workers & Pages → твой воркер → Logs** (там будет видно,
дошло ли сообщение и что ответил GitHub), и/или пришли мне, что там
написано.

## Как откатить обратно на обычный опрос

Если что-то пошло не так и хочется вернуть как было:

```
https://api.telegram.org/bot<TOKEN>/deleteWebhook
```

и добавь обратно в `.github/workflows/telegram_on_demand.yml` под `on:`
строки:

```yaml
  schedule:
    - cron: "*/5 * * * *"
```
