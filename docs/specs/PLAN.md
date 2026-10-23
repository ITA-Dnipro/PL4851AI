# PLAN: реалізація EPIC-DEMO (публічний каталог інвесторів)

| Поле | Значення |
|---|---|
| Статус | **APPROVED (2026-10-23)** — план погоджено замовником; код ще не змінювався, очікується команда почати |
| Специфікація | `docs/specs/EPIC-DEMO.md` (статус: **APPROVED**, Q-1…Q-7 закрито) |
| Дата | 2026-10-23 |
| Гілка | Пропонується `feature/investors-public-api` від `main` (зараз `main`, робоче дерево чисте, окрім `docs/specs/`) |

> Позначки: **[P-n]** — припущення плану (розділ 7), **[R-n]** — ризик (розділ 6). Q-n — відкриті питання зі специфікації.

## 0. Передумова: специфікація ще не погоджена

`EPIC-DEMO.md` має статус DRAFT, а питання Q-1…Q-7 лишаються без відповідей. План нижче складений так, щоб **не залежати від них там, де це можливо**, а решту ізолює:

| Питання | Вплив на план | Рішення плану за замовчуванням |
|---|---|---|
| Q-1 невідомий `type` | Лише NS-03, фільтр за типом | Зріз 1 не включає фільтр; у зрізі 2 — 400 (рекомендація специфікації). |
| Q-2 людська назва типу | Серіалізатор | Тільки код (`fund`), як в Issue. |
| Q-3 показ `private` | Правило видимості | Показуємо всіх `is_verified=True` (за Issue). |
| Q-4 санітизація опису | Серіалізатор деталей | Повертаємо `investor_description` як є (див. R-5). |
| Q-5 `slug` | Модель, міграція | Не додаємо. |
| Q-6 UUID чи ціле | Модель | Лишаємо `investor_id` (ціле). |
| Q-7 місце фікстури | Файл | `investors/fixtures/` (за Issue). |

Якщо ви відповісте на Q-n інакше, зміняться тільки позначені рядки таблиці в розділі 3.

## 1. Карта файлів

| Файл | Дія | Призначення |
|---|---|---|
| `backend/investors/serializers.py` | **Новий** | `InvestorListSerializer`, `InvestorPublicProfileSerializer` |
| `backend/investors/views.py` | **Змінюється** (зараз коментар-заглушка) | `InvestorPagination`, `InvestorProfileListView`, `InvestorPublicProfileDetailView` |
| `backend/investors/urls.py` | **Новий** | Маршрути `''` і `'<int:id>/'`, `app_name = 'investors'` |
| `backend/config/urls.py` | **Змінюється** (1 рядок) | `path('api/investors/', include('investors.urls', namespace='investors'))` |
| `backend/investors/fixtures/investors.json` | **Новий** | Користувачі + верифіковані та неверифікований інвестори |
| `backend/investors/tests/__init__.py` | **Новий** | Пакет тестів |
| `backend/investors/tests/test_investors_views.py` | **Новий** | API-тести за AC/NS |
| `backend/README.md` | **Змінюється** (необов'язково) | Короткий опис ендпоінтів |

**Не змінюємо:** `investors/models.py`, міграції, `admin.py`, `settings.py`, `startups/*`, `projects/*`, `dashboard/*`, frontend, `fixtures/*.json`, залежності. Нових міграцій немає (C-06).

## 2. Найменший вертикальний зріз для демонстрації

**Зріз 1 («список + деталі, що працюють наскрізь»)** — завершується за 5 кроків (розділ 4):

- `GET /api/investors/` — пагінація 8 / `page_size`, лише `is_verified=True`, порядок за `investor_id`, 4 поля (FR-01, 02, 03, 08, 10, 11, 12).
- `GET /api/investors/{id}/` — 7 полів, 404 для невідомого й неверифікованого (FR-06, 07, 08, 09).
- Фікстура, що завантажується одним `loaddata` (FR-13) — потрібна, щоб на демонстрації було що показати.
- Тести на ці вимоги: AC-01, AC-02, AC-03, AC-06, AC-07, AC-08, NS-01, NS-02, NS-08.

**Чому саме так:** це мінімум, який можна показати наживо (`curl`/браузер у `BrowsableAPIRenderer`) і який дає цінність без жодного відкритого питання (Q-1…Q-7 його не блокують). Зріз торкається 5 файлів, нових залежностей і міграцій немає.

**Зріз 2 («пошук і фільтр») — якщо лишається час:** FR-04 `search`, FR-05 `type` (+ рішення Q-1), AC-04, AC-05, NS-03, NS-06. Це ще ~15 рядків у view та 3–4 тести.

**Зріз 3 («завершеність»):** решта NS (NS-04, 05, 07, 09), AC-09…AC-11, FR-14 повністю, README.

**Що не робимо на демонстрації:** frontend, `dashboard`/`tracking` (#100–#110), OpenAPI.

## 3. План по кожній вимозі

Позначки в колонці «Зріз»: **1** — входить у вертикальний зріз, **2** — розширення, **3** — завершення.

| ID | Файли | Зміни | Тестові сценарії | Ризики | Зріз |
|---|---|---|---|---|---|
| **FR-01** | `investors/views.py`, `investors/urls.py`, `config/urls.py` | `ListAPIView` із `pagination_class`; маршрут `''`; підключення в `config/urls.py` | AC-01: 10 верифікованих → `count=10`, 8 в `results`, `next` не `null`; перевірка ключів `count/next/previous/results` | R-1 (глобальної пагінації немає, її треба задати у view) | 1 |
| **FR-02** | `investors/serializers.py` | `InvestorListSerializer` з полями `investor_id`, `investor_name`, `investor_type`, `investment_min` | AC-01: набір ключів елемента дорівнює рівно 4 полям; AC-10 (немає `user`, `edrpou_or_ipn`) | Випадкове додавання зайвих полів; зловживання `__all__` — заборонити | 1 |
| **FR-03** | `investors/views.py` | `InvestorPagination(PageNumberPagination)`: `page_size=8`, `page_size_query_param='page_size'` | AC-02 (`?page=2` → 2 елементи, `previous` не `null`, `next` `null`); AC-03 (`?page_size=3`); NS-04 (`?page=99` → 404); NS-05 | R-2: у `StartupPagination` немає `max_page_size` — без ліміту `?page_size=100000` віддасть усе. Пропонується `max_page_size=100` (як у `ProjectPagination`), див. P-3 | 1 (AC-02/03), 3 (NS) |
| **FR-04** | `investors/views.py` | `filter_backends=[filters.SearchFilter]`, `search_fields=['investor_name']` | AC-04: `?search=green` лише збіги без урахування регістру; NS-06: `?search=zzz` → `count=0` | `SearchFilter` шукає за підрядком (`icontains`), не за словами; це збігається з A-10 | 2 |
| **FR-05** | `investors/views.py` | У `get_queryset` читати `type`, фільтрувати за `investor_type` | AC-05: `?type=fund` лише фонди; NS-03: `?type=unknown` (за Q-1) | R-3: невизначена поведінка при невідомому значенні (Q-1). Рекомендовано 400 через перевірку проти `InvestorType.values`; це додає ~5 рядків | 2 |
| **FR-06** | `investors/serializers.py`, `investors/views.py`, `investors/urls.py` | `InvestorPublicProfileSerializer` (7 полів), `RetrieveAPIView` з `lookup_field='investor_id'`, `lookup_url_kwarg='id'`; маршрут `'<int:id>/'` | AC-07: тіло за схемою FR-06 | R-4: `contact` — вкладений об'єкт, а не поле моделі; потрібен `SerializerMethodField` | 1 |
| **FR-07** | `investors/serializers.py` | `contact = {'phone': obj.investor_phone}` | AC-07: `contact == {'phone': ...}`; NS-09: порожній телефон → `""` | R-6: у `InvestorProfile` телефон **не нормалізується** (на відміну від стартапів); у `initial_data.json` він `380671112233` без `+`. Прикладова відповідь Issue (`+380…`) збігається лише якщо так збережено | 1 |
| **FR-08** | `investors/views.py` | `queryset = InvestorProfile.objects.filter(is_verified=True)` у **обох** view | AC-06: неверифікований відсутній у списку, `count` його не враховує; NS-02 (деталі → 404) | Єдина точка помилки: забути фільтр в одному з двох view. Виносити фільтр у спільний метод/міксин | 1 |
| **FR-09** | `investors/views.py` | Стандартний 404 від `RetrieveAPIView` по відфільтрованому queryset | NS-01: `id=999` → 404; NS-02: неверифікований → 404 і те саме тіло, що й для неіснуючого | Не розкривати існування (однакова відповідь) | 1 |
| **FR-10** | `investors/views.py` | `permission_classes = [permissions.AllowAny]` явно (як у `StartupPublicProfileDetailView`) | AC-08: запит без токена → 200 | R-7: глобально `AllowAny`, але явна вказівка захищає від зміни глобальних налаштувань | 1 |
| **FR-11** | `investors/views.py` | `.order_by('investor_id')` | AC-09: два запити поспіль дають однаковий порядок, зростання за `investor_id` | Без `order_by` пагінація дасть `UnorderedObjectListWarning` і нестабільні сторінки (у моделі немає `Meta.ordering`) | 1 |
| **FR-12** | `investors/serializers.py` | `DecimalField` за замовчуванням дає рядок; `null`, якщо `None` | AC-07: `"50000.00"`; NS-08: `null` | R-8: поведінка залежить від `COERCE_DECIMAL_TO_STRING` (за замовч. `True`, у `settings.py` не змінювалось) | 1 |
| **FR-13** | `investors/fixtures/investors.json` | Користувачі з `role='investor'` + ≥2 верифіковані, ≥1 неверифікований, ≥1 з `investment_min=null`, ≥1 з порожнім телефоном | AC-11: `call_command('loaddata', 'investors')` без помилок + перевірка складу | R-9: `fixtures/initial_data.json` містить `"username"`, а `User.username = None`; цей формат **не** копіювати. Первинні ключі брати з незайнятого діапазону (напр., 901+), щоб не конфліктувати з іншими фікстурами | 1 |
| **FR-14** | `investors/tests/test_investors_views.py` | Тест-клас `APITestCase`; дані створюються в `setUp` через `User.objects.create_user(...)` та `InvestorProfile.objects.create(...)` (як у `tests/test_models/test_investors.py`) | Усе перелічене вище | R-10: фікстури з `startups` у тестах не використовувати (залежності між файлами) | 1 → 3 |
| **C-04** (безпека) | `investors/serializers.py` | Явний перелік полів; `user`, `edrpou_or_ipn` у відповідь не входять | AC-10: відсутність ключів `user`, `edrpou_or_ipn`, `email` у обох ендпоінтах | Регрес при майбутньому додаванні полів у модель — захищає явний перелік | 1 |
| **C-02/C-03** (стиль, маркери) | усі нові `.py` | black, isort, flake8-quotes (одинарні лапки); `pytestmark = pytest.mark.api` | `pytest --strict-markers` проходить | Маркер `api` обов'язковий через `--strict-markers` лише якщо він використаний; пропуск не ламає тести | 1 |

## 4. Порядок виконання (кроки зрізу 1)

| Крок | Дія | Перевірка після кроку |
|---|---|---|
| 1 | Гілка `feature/investors-public-api`. Написати **тести спершу** (червоні): AC-01, 02, 03, 06, 07, 08; NS-01, 02, 08 | `pytest investors/tests -q` — тести падають з 404 (маршруту ще немає) |
| 2 | `serializers.py`: обидва серіалізатори | імпорт без помилок: `python manage.py check` |
| 3 | `views.py` + `urls.py` + підключення в `config/urls.py` | `pytest investors/tests` — зелені |
| 4 | Фікстура + тест `loaddata` (AC-11) | `python manage.py loaddata investors` на чистій БД |
| 5 | Лінтери та повний прогін | `pytest` (весь backend), `pre-commit run --files <змінені файли>` |

Кожен крок — окремий коміт; перед коммітом показую diff. Повідомлення комітів англійською, у стилі історії репозиторію.

## 5. Як перевірити на демонстрації

```bash
docker compose up --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py loaddata investors
# список
curl "http://localhost:8000/api/investors/"
curl "http://localhost:8000/api/investors/?page_size=2&page=2"
# деталі та 404
curl "http://localhost:8000/api/investors/<id верифікованого>/"
curl -i "http://localhost:8000/api/investors/<id неверифікованого>/"
```

Окрім `curl`, обидва URL відкриваються в браузері завдяки `BrowsableAPIRenderer`.

## 6. Ризики

| ID | Ризик | Імовірність / вплив | Пом'якшення |
|---|---|---|---|
| R-1 | Немає глобальної пагінації; без `pagination_class` відповідь не матиме `count/next/previous` | Висока / середній | Задавати `pagination_class` у view (є в плані). |
| R-2 | Необмежений `page_size` (в `StartupPagination` немає `max_page_size`) | Середня / середній | Додати `max_page_size=100` (P-3), потребує вашого підтвердження. |
| R-3 | Невизначена поведінка при невідомому `type` (Q-1) | Висока / низький | Зріз 1 не включає `type`; рішення — у зрізі 2. |
| R-4 | Вкладений `contact` не збігається з плоскою моделлю | Низька / низький | `SerializerMethodField`. |
| R-5 | `investor_description` повертається без санітизації; поле — довільний `TextField`. У стартапах для цього використовуються `bleach`/`markdown` (#58). Можливий XSS при виводі на frontend | Середня / середній | Q-4; у плані — повертати як є, і явно позначити для frontend як текст, не HTML. Якщо потрібна санітизація, це +10 рядків і окремі тести. |
| R-6 | Телефон не нормалізований (формат `+380…` проти `380…`) | Висока / низький | Повертаємо як збережено; не змінювати модель; зафіксовано в AC-07. |
| R-7 | Залежність від глобального `AllowAny` | Низька / середній | Явний `permission_classes`. |
| R-8 | Залежність від `COERCE_DECIMAL_TO_STRING` | Низька / низький | Тест на `"50000.00"`. |
| R-9 | Некоректна фікстура: шаблон `initial_data.json` містить неіснуюче поле `username` | Висока / середній | Складати фікстуру за фактичними полями `User`; перевірити `loaddata` на чистій БД (крок 4). |
| R-10 | Тести залежать від спільних фікстур | Середня / середній | Дані тестів створюються в `setUp`. |
| R-11 | Конфлікт PK у фікстурах при спільному завантаженні | Низька / низький | Діапазон 901+. |
| R-12 | Тести на SQLite локально, на Postgres у Docker — різна поведінка `icontains`/сортування | Низька / низький | Для зрізу 1 різниці немає; для `search` перевірити на обох. |
| R-13 | Ітерація може зачепити роботу над Epic #89 (`config/urls.py`, спільні файли) | Низька / середній | Конфліктних рядків лише один (`config/urls.py`); окрема гілка від `main`. |
| R-14 | `EPIC-DEMO` не погоджений | Висока / високий | Цей план потребує вашого явного підтвердження (розділ 8). |

## 7. Припущення плану (потребують підтвердження)

| ID | Припущення |
|---|---|
| P-1 | Працюємо в гілці `feature/investors-public-api` від `main`. |
| P-2 | Тести пишемо **до** реалізації (TDD) і створюємо дані в `setUp`, а не через спільні фікстури. |
| P-3 | Додаємо `max_page_size=100` (відхилення від `StartupPagination`, але збігається з `ProjectPagination`). У специфікації цього немає — потребує вашого дозволу. |
| P-4 | Фікстура створює власних користувачів з PK 901+. |
| P-5 | `investor_description` повертається без санітизації (Q-4 відкладено). |
| P-6 | README оновлюємо коротко (розділ про ендпоінти), у зрізі 3. |
| P-7 | Один коміт на крок плану; змін у міграціях, моделях і залежностях немає. |
| P-8 | Щоб не розширювати обсяг, `type` у зрізі 2 перевіряється проти `InvestorType.values` і повертає 400 (рекомендація Q-1). |

## 8. Підтвердження

Прошу підтвердити або виправити:

- [ ] Вертикальний зріз 1 (розділ 2) як обсяг демонстрації; зріз 2 — якщо вистачить часу.
- [ ] Припущення P-1…P-8, зокрема **P-3** (`max_page_size`) та **P-5** (без санітизації).
- [x] Q-1 і Q-4 закрито «за замовчуванням» (Q-1 = 400, Q-4 = без санітизації); Q-2, Q-3, Q-5, Q-6, Q-7 — за значеннями з розділу 0.
- [ ] Погодження самої `EPIC-DEMO.md` (зараз DRAFT).

**Погоджено замовником 2026-10-23** (вертикальний зріз 1, припущення P-1…P-8, специфікація). Код не змінюється до команди почати.
