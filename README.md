# Roomly hub: система бронювання готелів

Лабораторна робота №4 (2 рівень). Реляційна база даних у PostgreSQL з консольним застосунком і вебзастосунком на Flask.

**Автор:** Матяш Дарія Сергіївна
**Група:** ІПЗ-31
**Звіт:** [docs/report.md](docs/report.md)

## Можливості

- 7 таблиць у третій нормальній формі, обмеження цілісності, захист від подвійного бронювання (`EXCLUDE`)
- 4 збережені процедури, 4 тригери, 3 представлення
- Консольний застосунок (CRUD для гостей, номерів і бронювань)
- Вебзастосунок на Flask: CRUD, пошук вільних номерів, оплати, послуги, валідація на сервері, CSRF-захист

## Структура репозиторію

```
lab04-database/
├── README.md
├── docker-compose.yml
├── docs/                          # звіт, ER-діаграма та скріншоти
│   ├── report.md
│   ├── conceptual_model.png
│   └── *.png
├── database/                      # SQL-скрипти (виконуються автоматично при першому запуску)
│   ├── 01_create_tables.sql
│   ├── 02_insert_data.sql
│   ├── 03_create_procedures.sql
│   ├── 04_create_triggers.sql
│   ├── 05_create_views.sql
│   └── queries/
│       └── queries.sql
├── console_app/                   # консольний застосунок
│   ├── main.py
│   ├── database.py
│   └── requirements.txt
└── web_app/                       # Flask-застосунок
    ├── app.py
    ├── database.py
    ├── validators.py
    ├── requirements.txt
    ├── static/
    └── templates/
```

## Вимоги

- Docker Desktop
- Python 3.10+

## Запуск

### 1. База даних

```bash
docker compose up -d
```

Скрипти з `database/` виконаються автоматично при першому запуску. Щоб скинути базу й створити її заново:

```bash
docker compose down -v
docker compose up -d
```

Параметри підключення: `localhost:5432`, база `hotel_booking`, користувач `postgres`, пароль `password`.

### 2. Консольний застосунок

```bash
cd console_app
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 3. Вебзастосунок

```bash
cd web_app
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Відкрийте http://127.0.0.1:5000

## SQL-запити

Усі запити (5 базових і 3 аналітичні) лежать у [database/queries/queries.sql](database/queries/queries.sql). Запускати їх зручно по одному в pgAdmin або через `psql`:

```bash
docker exec -it hotel_db psql -U postgres -d hotel_booking
```

## Технології

PostgreSQL 17, Docker, Python, psycopg2, Flask, Flask-WTF