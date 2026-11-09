GET /api/notifications/ (с ?unread=1), GET /api/notifications/{id}/, DELETE /api/notifications/{id}/.
POST /api/notifications/{id}/read/ и POST /api/notifications/read-all/ отмечают прочитанным.
GET /api/notifications/unread-count/
GET /api/bookings/my/ возвращает только записи клиента, с ?upcoming=1 только будущие.
POST /api/bookings/{id}/cancel/ отменяет свою запись, ответ 204. DELETE /api/bookings/{id}/ работает так же.



все эндпоинты в urls.py в папках roles и ceback к большинству можно делать весь crud даже по id

