# Web-Service
RESTful API service using microservices

* PostgreSQL
* Adminer
* Custom Python Flask Server

---

### How to run:
```
docker-compose -f web_service.yml up --build
```

Ports:
* adminer - 8080
* PostgreSQL - 5432
* server - 3333

### How to stop:
```
docker-compose -f web_service.yml down [--volumes]

or

docker-compose -f web_service.yml rm
```

---

The API can be used to store cities, countries and temperature records within
the cities.

Unicity and foreign key contraints are enforced.
