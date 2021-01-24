#!/usr/bin/env python3

"""
(C) Copyright 2020
"""

from decimal import Decimal
from time import sleep

import os

from flask import Flask, Response, request, json
from psycopg2.extras import RealDictCursor

import jsonschema
import psycopg2

APP = Flask(__name__)
CONN = None

class DecimalEncoder(json.JSONEncoder):
    """
    Clasa de conversie a numerelor reale cu virgulă din Decimal în float.
    """
    def default(self, obj):
        """
        Funcția auxiliară.

        Args:
            obj - obiectul de verificar / convertit.
        Returns:
            float: numărul convertit, dacă era Decimal
            object: dacă obiectul nu era Decimal
        """
        if isinstance(obj, Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)

def validate_json(json_data, json_schema):
    """
    Verifică dacă un obiect JSON respectă o anumită structură.

    Returns:
        True, dacă obiectul respectă formatul
        False, altfel
    """
    try:
        jsonschema.validate(instance=json_data, schema=json_schema)
    except jsonschema.exceptions.ValidationError:
        return False

    return True

def init_postgres():
    """
    Pornește conexiunea cu baza de date și verifică dacă există configurația de
    de tabele necesară. Dacă nu există, aceasta este creată.
    """
    global CONN

    host = "db"
    database = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "admin")
    password = os.getenv("POSTGRES_PASSWORD", "adminpass")

    # Rulează în buclă până pornește serverul bazei de date.
    while True:
        try:
            CONN = psycopg2.connect(host=host, database=database,
                                    user=user, password=password)
            cursor = CONN.cursor()

            # Creează tabelul „countries”, dacă nu există.
            cursor.execute("SELECT * FROM information_schema.tables WHERE "
                           "table_name=\'countries\'")
            if not bool(cursor.rowcount):
                cursor.execute(
                    """
                    CREATE TABLE countries (
                        country_id SERIAL PRIMARY KEY,
                        country_name VARCHAR(255) NOT NULL UNIQUE,
                        country_lat NUMERIC(6, 4) NOT NULL,
                        country_lon NUMERIC(7, 4) NOT NULL
                    )
                    """)

            # Creează tabelul „cities”, dacă nu există.
            cursor.execute("SELECT * FROM information_schema.tables WHERE "
                           "table_name=\'cities\'")
            if not bool(cursor.rowcount):
                cursor.execute(
                    """
                    CREATE TABLE cities (
                        city_id SERIAL PRIMARY KEY,
                        country_id INTEGER NOT NULL,
                        city_name VARCHAR(255) NOT NULL,
                        city_lat NUMERIC(6, 4) NOT NULL,
                        city_lon NUMERIC(7, 4) NOT NULL,
                        unique (country_id, city_name),
                        CONSTRAINT fk_country_id
                            FOREIGN KEY(country_id)
                            REFERENCES countries(country_id)
                            ON DELETE CASCADE
                            ON UPDATE CASCADE
                    )
                    """)

            # Creează tabelul „temperatures”, dacă nu există.
            cursor.execute("SELECT * FROM information_schema.tables WHERE "
                           "table_name=\'temperatures\'")
            if not bool(cursor.rowcount):
                cursor.execute(
                    """
                    CREATE TABLE temperatures (
                        temp_id SERIAL PRIMARY KEY,
                        temp_value NUMERIC(6, 4) NOT NULL,
                        temp_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                        city_id INTEGER NOT NULL,
                        unique (temp_timestamp, city_id),
                        CONSTRAINT fk_city_id
                            FOREIGN KEY(city_id)
                            REFERENCES cities(city_id)
                            ON DELETE CASCADE
                            ON UPDATE CASCADE
                    )
                    """)

            cursor.close()
            CONN.commit()

            return
        except psycopg2.OperationalError:
            sleep(1)

################################## Rute Tari ###################################

@APP.route("/api/countries", methods=["POST"])
def countries_post():
    """
    POST /api/countries

    Adaugă o țară în baza de date.

    Body: {nume: Str, lat: Double, lon: Double} - obiect
    Succes: 201 și { id: Int }
    Eroare: 400 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "nume": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
        "required": ["nume", "lat", "lon"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())
    values[0] = f"\'{values[0]}\'"
    values = ", ".join(map(str, values))
    columns = "country_name, country_lat, country_lon"
    query = """ INSERT INTO countries(%s) VALUES(%s) \
                RETURNING country_id; """ % (columns, values)

    try:
        cursor.execute(query)
        country_id = cursor.fetchone()[0]
    except psycopg2.errors.NumericValueOutOfRange:
        # Latitudinea sau Longitudinea au valori eronate (prea mari sau prea
        # mici).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.UniqueViolation:
        # Există deja o țară cu acel nume.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    CONN.commit()

    return Response(
        response=json.dumps({"id": country_id}),
        status=201,
        mimetype="application/json"
    )

@APP.route("/api/countries", methods=["GET"])
def countries_get():
    """
    GET /api/countries

    Întoarce toate intrările din baza de date.

    Succes: 200 și [ {id: Int, nume: Str, lat: Double, lon: Double}, {...}, ...]
    - lista de obiecte
    """

    cursor = CONN.cursor(cursor_factory=RealDictCursor)
    query = """ SELECT * FROM countries; """

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )

@APP.route("/api/countries/<int:country_id>", methods=["PUT"])
def countries_put(country_id=None):
    """
    PUT /api/countries/:id

    Modifică țara cu id-ul dat ca parametru.

    Body: {id: Int, nume: Str, lat: Double, lon: Double} - obiect
    Succes: 200
    Eroare: 400, 404 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "id" : {"type": "integer"},
            "nume": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
        "required": ["id", "nume", "lat", "lon"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid or country_id != payload["id"]:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())[1:]
    values[0] = f"\'{values[0]}\'"
    columns = ["country_name", "country_lat", "country_lon"]
    changes = []
    for col, val in zip(columns, map(str, values)):
        changes.append("%s=%s" % (col, val))

    query = """ UPDATE countries SET %s WHERE country_id=%d \
                RETURNING country_id; """ % (", ".join(changes), country_id)

    try:
        cursor.execute(query)
        num_updates = len(cursor.fetchall())
    except psycopg2.errors.NumericValueOutOfRange:
        # Latitudinea sau Longitudinea au valori eronate (prea mari sau prea
        # mici).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.UniqueViolation:
        # Există deja o țară cu acel nume.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    if num_updates == 0:
        # Țara de actualizat nu există în baza de date.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

@APP.route("/api/countries/<int:country_id>", methods=["DELETE"])
def countries_del(country_id=None):
    """
    DELETE /api/countries/:id

    Șterge țara cu id-ul dat ca parametru.

    Succes: 200
    Eroare: 404
    """

    cursor = CONN.cursor()

    query = """ DELETE FROM countries WHERE country_id=%d \
                RETURNING 1; """ % country_id

    cursor.execute(query)
    num_updates = len(cursor.fetchall())
    cursor.close()

    if num_updates == 0:
        # Țara de șters nu există în baza de date.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

################################## Rute Orase ##################################

@APP.route("/api/cities", methods=["POST"])
def cities_post():
    """
    POST /api/cities

    Adaugă un oraș în baza de date.

    Body: {idTara: Int, nume: Str, lat: Double, lon: Double} - obiect
    Succes: 201 și { id: Int }
    Eroare: 400, 404 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "idTara": {"type": "integer"},
            "nume": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
        "required": ["idTara", "nume", "lat", "lon"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())
    values[1] = f"\'{values[1]}\'"
    values = ", ".join(map(str, values))
    columns = "country_id, city_name, city_lat, city_lon"
    query = """ INSERT INTO cities(%s) VALUES(%s) \
                RETURNING city_id; """ % (columns, values)

    try:
        cursor.execute(query)
        city_id = cursor.fetchone()[0]
    except psycopg2.errors.NumericValueOutOfRange:
        # Latitudinea sau Longitudinea au valori eronate (prea mari sau prea
        # mici).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.ForeignKeyViolation:
        # Nu există o țară cu id-ul dat.
        CONN.rollback()
        return Response(status=404)
    except psycopg2.errors.UniqueViolation:
        # Există deja un oraș cu acest nume în aceeași țară.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    CONN.commit()

    return Response(
        response=json.dumps({"id": city_id}),
        status=201,
        mimetype="application/json"
    )

@APP.route("/api/cities", methods=["GET"])
def cities_get():
    """
    GET /api/cities

    Întoarce toate orașele din baza de date.

    Succes: 200 și
    [ {id: Int, idTara: Int, nume: Str, lat: Double, lon: Double}, {...}, ...]
    - lista de obiecte
    """

    cursor = CONN.cursor(cursor_factory=RealDictCursor)
    query = """ SELECT * FROM cities; """

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )

@APP.route("/api/cities/country/<int:country_id>", methods=["GET"])
def cities_by_country_get(country_id=None):
    """
    GET /api/cities/country/:idTara

    Întoarce toate orașele care aparțin de țara primită ca parametru.

    Succes: 200 și
    [ {id: Int, idTara: Int, nume: Str, lat: Double, lon: Double}, {...}, ...]
    - lista de obiecte
    """

    cursor = CONN.cursor(cursor_factory=RealDictCursor)
    query = """ SELECT * FROM cities WHERE country_id=%d; """ % country_id

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )

@APP.route("/api/cities/<int:city_id>", methods=["PUT"])
def cities_put(city_id=None):
    """
    PUT /api/cities/:id

    Modifică orașul cu id-ul dat ca parametru.

    Body: {id: Int, idTara: Int, nume: Str, lat: Double, lon: Double} - obiect
    Succes: 200
    Eroare: 400, 404 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "id" : {"type": "integer"},
            "idTara" : {"type": "integer"},
            "nume": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
        "required": ["id", "idTara", "nume", "lat", "lon"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid or city_id != payload["id"]:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())[1:]
    values[1] = f"\'{values[1]}\'"
    columns = ["country_id", "city_name", "city_lat", "city_lon"]
    changes = []
    for col, val in zip(columns, map(str, values)):
        changes.append("%s=%s" % (col, val))

    query = """ UPDATE cities SET %s WHERE city_id=%d \
                RETURNING city_id; """ % (", ".join(changes), city_id)

    try:
        cursor.execute(query)
        num_updates = len(cursor.fetchall())
    except psycopg2.errors.NumericValueOutOfRange:
        # Latitudinea sau Longitudinea au valori eronate (prea mari sau prea
        # mici).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.ForeignKeyViolation:
        # Țara cu id-ul dat nu există.
        CONN.rollback()
        return Response(status=404)
    except psycopg2.errors.UniqueViolation:
        # Există deja un oraș cu același nume în aceeași țară.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    if num_updates == 0:
        # Orașul de actualizat nu există.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

@APP.route("/api/cities/<int:city_id>", methods=["DELETE"])
def cities_del(city_id=None):
    """
    DELETE /api/cities/:id

    Șterge orașul cu id-ul dat ca parametru.

    Succes: 200
    Eroare: 404
    """

    cursor = CONN.cursor()

    query = """ DELETE FROM cities WHERE city_id=%d RETURNING 1; """ % city_id

    cursor.execute(query)
    num_updates = len(cursor.fetchall())
    cursor.close()

    if num_updates == 0:
        # Orașul de șters nu există.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

############################### Rute Temperaturi ###############################

@APP.route("/api/temperatures", methods=["POST"])
def temp_post():
    """
    POST /api/temperatures

    Adaugă o temperatură în baza de date.

    Body: {idOras: Int, valoare: Double} - obiect
    Succes: 201 și { id: Int }
    Eroare: 400, 404 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "idOras": {"type": "integer"},
            "valoare": {"type": "number"},
        },
        "required": ["idOras", "valoare"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())
    values = ", ".join(map(str, values))
    columns = "city_id, temp_value"
    query = """ INSERT INTO temperatures(%s) VALUES(%s) \
                RETURNING temp_id; """ % (columns, values)

    try:
        cursor.execute(query)
        temp_id = cursor.fetchone()[0]
    except psycopg2.errors.NumericValueOutOfRange:
        # Valoarea este eronată (prea mare sau prea mică).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.ForeignKeyViolation:
        # Orașul cu id-ul dat nu există.
        CONN.rollback()
        return Response(status=404)
    except psycopg2.errors.UniqueViolation:
        # Există deja o intrare din același oraș cu același timestamp.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    CONN.commit()

    return Response(
        response=json.dumps({"id": temp_id}),
        status=201,
        mimetype="application/json"
    )

@APP.route("/api/temperatures", methods=["GET"])
def temp_get():
    """
    GET /api/temperatures?lat=Double&lon=Double&from=Date&until=Date

    Întoarce temperaturi, în funcție de latitudine, longitudine, data de
    început și/sau data de final. Ruta va răspunde indiferent de ce parametri de
    cerere se dau. Dacă nu se trimite niciunul, se vor întoarce toate
    temperaturile. Dacă se dă doar o coordonată, se face match pe ea. Dacă se dă
    doar un capăt de interval, se respectă capătul de interval. Dacă vreunul din
    parametri are un tip de date greșit, nu se întoarce nimic.

    Succes: 200 și [ {id: Int, valoare: Double, timestamp: Date}, {...}, ...]
    - lista de obiecte
    """

    # Condiția este construită bucată cu bucată.
    condition = ""

    lat = request.args.get("lat")
    if lat is not None:
        condition += "cities.city_lat=%s " % lat

    lon = request.args.get("lon")
    if lon is not None:
        if condition != "":
            condition += "and "
        condition += "cities.city_lon=%s " % lon

    from_date = request.args.get("from")
    if from_date is not None:
        if condition != "":
            condition += "and "
        condition += "temperatures.temp_timestamp >= \'" + from_date + \
                    "\'::timestamp "

    until_date = request.args.get("until")
    if until_date is not None:
        if condition != "":
            condition += "and "
        condition += "temperatures.temp_timestamp < \'" + until_date + \
                    "\'::timestamp + \'1 day\'::interval "

    cursor = CONN.cursor(cursor_factory=RealDictCursor)

    if condition == "":
        # Dacă cererea nu a avut argumente în URL.
        query = """ SELECT city_id, temp_id, temp_value,           \
                    TO_CHAR(temp_timestamp,'YYYY-MM-DD HH:MI:SS')  \
                    AS temp_timestamp                              \
                    FROM temperatures; """
    else:
        # Dacă cererea a avut argumente.
        query = """ SELECT temperatures.city_id, temperatures.temp_id,         \
                    temperatures.temp_value,                                   \
                    TO_CHAR(temperatures.temp_timestamp,'YYYY-MM-DD HH:MI:SS') \
                    AS temp_timestamp                                          \
                    FROM temperatures INNER JOIN cities                        \
                    ON temperatures.city_id = cities.city_id                   \
                    WHERE %s ; """ % condition

    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except psycopg2.Error:
        # Unul din parametri a avut tipul greșit, deci nu se întoarce nimic.
        results = []
        CONN.rollback()
    finally:
        cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )

@APP.route("/api/temperatures/cities/<int:city_id>", methods=["GET"])
def temp_by_city_get(city_id=None):
    """
    GET /api/temperatures/cities/:idOras?from=Date&until=Date

    Întoarce temperaturile pentru orașul dat ca parametru de cale, în funcție
    de data de început și/sau data de final. Ruta va răspunde indiferent de ce
    parametri de cerere se dau. Dacă nu se trimite nimic, se vor întoarce toate
    temperaturile pentru orașul respectiv. Dacă se dă doar un capăt de interval,
    se respectă capătul de interval. Dacă vreunul din parametri are un tip de
    date greșit, nu se întoarce nimic.

    Succes: 200 și [{id: Int, valoare: Double, timestamp: Date}, {...}, ...]
    - lista de obiecte
    """

    # Condiția este construită bucată cu bucată.
    date_cond = ""

    from_date = request.args.get("from")
    if from_date is not None:
        date_cond = "temp_timestamp >= \'" + from_date + "\'::timestamp "

    until_date = request.args.get("until")
    if until_date is not None:
        if date_cond != "":
            date_cond += "and "
        date_cond += "temp_timestamp < \'" + until_date + \
                    "\'::timestamp + \'1 day\'::interval "

    condition = "WHERE city_id=%d" % city_id

    if date_cond != "":
        condition += " and " + date_cond

    cursor = CONN.cursor(cursor_factory=RealDictCursor)

    query = """ SELECT city_id, temp_id, temp_value,          \
                TO_CHAR(temp_timestamp,'YYYY-MM-DD HH:MI:SS') \
                AS temp_timestamp                             \
                FROM temperatures %s; """ % condition

    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except psycopg2.Error:
        # Unul din parametrii a avut tipul greșit, deci nu se întoarce nimic.
        results = []
        CONN.rollback()
    finally:
        cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )


@APP.route("/api/temperatures/countries/<int:country_id>", methods=["GET"])
def temp_by_country_get(country_id=None):
    """
    GET /api/temperatures/countries/:idTara?from=Date&until=Date

    Întoarce temperaturile pentru țara dată ca parametru de cale, în funcție de
    data de inceput și/sau data de final. Ruta va raspunde indiferent de ce
    parametri de cerere se dau. Dacă nu se trimite nimic, se vor întoarce toate
    temperaturile pentru țara respectivă. Dacă se dă doar un capăt de interval,
    se respecta capătul de interval.

    Succes: 200 și [{id: Int, valoare: Double, timestamp: Date}, {...}, ...]
    - lista de obiecte
    """

    # Condiția este construită bucată cu bucată.
    date_cond = ""

    from_date = request.args.get("from")
    if from_date is not None:
        date_cond = "temp_timestamp >= \'" + from_date + "\'::timestamp "

    until_date = request.args.get("until")
    if until_date is not None:
        if date_cond != "":
            date_cond += "and "
        date_cond += "temp_timestamp < \'" + until_date + \
                    "\'::timestamp + \'1 day\'::interval "

    condition = "WHERE countries.country_id=%d" % country_id

    if date_cond != "":
        condition += " and " + date_cond

    cursor = CONN.cursor(cursor_factory=RealDictCursor)

    query = """ SELECT temperatures.city_id, temperatures.temp_id,             \
                temperatures.temp_value,                                       \
                TO_CHAR(temperatures.temp_timestamp,'YYYY-MM-DD HH:MI:SS')     \
                AS temp_timestamp                                              \
                FROM temperatures INNER JOIN cities                            \
                ON temperatures.city_id = cities.city_id INNER JOIN countries  \
                ON cities.country_id = countries.country_id %s; """ % condition

    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except psycopg2.Error:
        # Unul din parametrii a avut tipul greșit, deci nu se întoarce nimic.
        results = []
        CONN.rollback()
    finally:
        cursor.close()

    return Response(
        response=json.dumps(results, cls=DecimalEncoder),
        status=200,
        mimetype="application/json"
    )

@APP.route("/api/temperatures/<int:temp_id>", methods=["PUT"])
def temp_put(temp_id=None):
    """
    PUT /api/countries/:id

    Modifică temperatura cu id-ul dat ca parametru.

    Body: {id: Int, idOras: Int, valoare: Double} - obiect
    Succes: 200
    Eroare: 400, 404 sau 409
    """

    body_schema = {
        "type": "object",
        "properties": {
            "id" : {"type": "integer"},
            "idOras" : {"type": "integer"},
            "valoare": {"type": "number"},
        },
        "required": ["id", "idOras", "valoare"],
    }

    payload = request.get_json(silent=True)
    is_valid = validate_json(payload, body_schema)

    if not is_valid or temp_id != payload["id"]:
        return Response(status=400)

    cursor = CONN.cursor()

    values = list(payload.values())[1:]
    columns = ["city_id", "temp_value"]
    changes = []
    for col, val in zip(columns, map(str, values)):
        changes.append("%s=%s" % (col, val))

    query = """ UPDATE temperatures SET %s WHERE temp_id=%d \
                RETURNING temp_id; """ % (", ".join(changes), temp_id)

    try:
        cursor.execute(query)
        num_updates = len(cursor.fetchall())
    except psycopg2.errors.NumericValueOutOfRange:
        # Valoarea este eronată (prea mare sau prea mică).
        CONN.rollback()
        return Response(status=400)
    except psycopg2.errors.ForeignKeyViolation:
        # Orașul cu id-ul dat nu există.
        CONN.rollback()
        return Response(status=404)
    except psycopg2.errors.UniqueViolation:
        # Există deja o temperatură în același oraș și cu același timestamp.
        CONN.rollback()
        return Response(status=409)
    finally:
        cursor.close()

    if num_updates == 0:
        # Temperatura cu id-ul dat nu există.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

@APP.route("/api/temperatures/<int:temp_id>", methods=["DELETE"])
def temp_del(temp_id=None):
    """
    DELETE /api/cities/:temp_id

    Șterge temperatura cu id-ul dat ca parametru.

    Succes: 200
    Eroare: 404
    """

    cursor = CONN.cursor()

    query = """ DELETE FROM temperatures \
                WHERE temp_id=%d RETURNING 1; """ % temp_id

    cursor.execute(query)
    num_updates = len(cursor.fetchall())
    cursor.close()

    if num_updates == 0:
        # Temperatura cu id-ul dat nu există.
        return Response(status=404)

    CONN.commit()

    return Response(status=200)

##################################### Main #####################################

def main():
    """
    Entrypoint-ul programului.
    Aplicația reprezintă un web backend ce lucrează cu o bază de date.
    """
    init_postgres()

    addr = os.getenv("WEB_SERVICE_ADDR", "0.0.0.0")
    port = os.getenv("WEB_SERVICE_PORT", "80")
    APP.run(host=addr, port=int(port), debug=True)
    # Pentru rulare în mediu de producție se decomentează liniile 885 și 886 și
    # se șterge linia 879.
    # Se adaugă și următorul import: from gevent.pywsgi import WSGIServer
    # Totuși, voi lăsa serverul în debugging mode, pentru vizualizare mai
    # ușoară a efectelor cererilor.
    # http_server = WSGIServer(('', 80), APP)
    # http_server.serve_forever()

if __name__ == "__main__":
    main()
