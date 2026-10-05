"""End-to-end tests through the Flask test client (forms, roles, redirects)."""

from app.extensions import db
from app.models import STATUS_CANCELLED, STATUS_CONFIRMED, Appointment, User
from tests.helpers import ADMIN, ALICE, BOB, DOCTOR, USER_PW, slot_value, tomorrow_at


def login(client, email, password=USER_PW, **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def book(client, doctor_id, start):
    return client.post(
        "/patient/book",
        data={"doctor_id": doctor_id, "start": slot_value(start)},
        follow_redirects=True,
    )


def only_appointment_id(app):
    with app.app_context():
        return db.session.query(Appointment).one().id


def appointment_status(app, appointment_id):
    with app.app_context():
        return db.session.get(Appointment, appointment_id).status


# --- accounts -------------------------------------------------------------------------


def test_home_page_loads_for_visitors(client):
    assert client.get("/").status_code == 200


def test_registering_creates_a_patient_and_logs_them_in(app, client):
    response = client.post(
        "/register",
        data={"name": "New Person", "email": "New@Example.com", "password": "long-enough-1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.request.path == "/patient/doctors"
    with app.app_context():
        user = db.session.query(User).filter_by(email="new@example.com").one()
        assert user.role == "patient"
        assert user.password_hash != "long-enough-1"


def test_registration_rejects_duplicates_and_weak_input(client, data):
    duplicate = client.post(
        "/register", data={"name": "Alice 2", "email": ALICE, "password": "long-enough-1"}
    )
    assert duplicate.status_code == 400
    assert b"already exists" in duplicate.data

    short = client.post("/register", data={"name": "X", "email": "x@example.com", "password": "a"})
    assert short.status_code == 400
    bad_email = client.post(
        "/register", data={"name": "X", "email": "not-an-email", "password": "long-enough-1"}
    )
    assert bad_email.status_code == 400


def test_wrong_password_is_rejected(client, data):
    response = login(client, ALICE, "wrong-password")
    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_logout_ends_the_session(client, data):
    login(client, ALICE)
    client.post("/logout")
    response = client.get("/patient/appointments")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_ignores_an_external_next_url(client, data):
    response = client.post(
        "/login?next=https://evil.example/", data={"email": ALICE, "password": USER_PW}
    )
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


# --- access control -------------------------------------------------------------------


def test_anonymous_visitors_are_sent_to_the_login_page(client):
    response = client.get("/patient/doctors")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_roles_cannot_open_each_others_pages(app, client, data):
    login(client, ALICE)
    assert client.get("/admin/").status_code == 403
    assert client.get("/doctor/schedule").status_code == 403

    doctor_client = app.test_client()
    login(doctor_client, DOCTOR)
    assert doctor_client.get("/patient/doctors").status_code == 403
    assert doctor_client.get("/admin/").status_code == 403


def test_post_without_a_csrf_token_is_rejected(csrf_app):
    response = csrf_app.test_client().post("/login", data={"email": ALICE, "password": USER_PW})
    assert response.status_code == 400


def test_security_headers_are_set(client):
    headers = client.get("/login").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in headers["Content-Security-Policy"]


# --- patient journey ------------------------------------------------------------------


def test_search_and_slot_listing(client, data):
    login(client, ALICE)
    assert b"Grey" in client.get("/patient/doctors?q=cardio").data
    assert b"Grey" not in client.get("/patient/doctors?q=dermatology").data

    page = client.get(f"/patient/doctors/{data['doctor_id']}?date={tomorrow_at(9).date()}")
    assert b"9:00 AM" in page.data


def test_patient_books_and_sees_only_their_own_appointments(app, client, data):
    login(client, ALICE)
    response = book(client, data["doctor_id"], tomorrow_at(9))
    assert b"Appointment confirmed" in response.data
    assert b"Grey" in response.data

    other = app.test_client()
    login(other, BOB)
    assert b"Grey" not in other.get("/patient/appointments").data


def test_booking_a_taken_slot_shows_an_error(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))

    other = app.test_client()
    login(other, BOB)
    response = book(other, data["doctor_id"], tomorrow_at(9))
    assert b"already booked" in response.data


def test_patient_can_cancel_and_the_slot_reopens(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    appointment_id = only_appointment_id(app)

    response = client.post(f"/patient/appointments/{appointment_id}/cancel", follow_redirects=True)
    assert b"Appointment cancelled" in response.data
    assert appointment_status(app, appointment_id) == STATUS_CANCELLED

    other = app.test_client()
    login(other, BOB)
    assert b"Appointment confirmed" in book(other, data["doctor_id"], tomorrow_at(9)).data


def test_patient_can_reschedule(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    appointment_id = only_appointment_id(app)

    response = client.post(
        f"/patient/appointments/{appointment_id}/reschedule",
        data={"start": slot_value(tomorrow_at(10))},
        follow_redirects=True,
    )
    assert b"Appointment rescheduled" in response.data
    with app.app_context():
        assert db.session.get(Appointment, appointment_id).start_time == tomorrow_at(10)


def test_patient_cannot_modify_someone_elses_appointment(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    appointment_id = only_appointment_id(app)

    other = app.test_client()
    login(other, BOB)
    assert other.post(f"/patient/appointments/{appointment_id}/cancel").status_code == 403
    assert other.get(f"/patient/appointments/{appointment_id}/reschedule").status_code == 403
    reschedule = other.post(
        f"/patient/appointments/{appointment_id}/reschedule",
        data={"start": slot_value(tomorrow_at(11))},
    )
    assert reschedule.status_code == 403
    assert appointment_status(app, appointment_id) == STATUS_CONFIRMED


def test_malformed_booking_requests_are_rejected_cleanly(client, data):
    login(client, ALICE)
    assert client.post("/patient/book", data={"doctor_id": "x", "start": "y"}).status_code == 404
    bad_time = client.post("/patient/book", data={"doctor_id": data["doctor_id"], "start": "soon"})
    assert bad_time.status_code == 400


# --- doctor and admin -----------------------------------------------------------------


def test_doctor_sees_bookings_and_cannot_complete_a_future_one(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    appointment_id = only_appointment_id(app)

    doctor_client = app.test_client()
    login(doctor_client, DOCTOR)
    schedule = doctor_client.get(f"/doctor/schedule?date={tomorrow_at(9).date()}")
    assert b"Alice" in schedule.data

    response = doctor_client.post(
        f"/doctor/appointments/{appointment_id}/complete", follow_redirects=True
    )
    assert b"has not started yet" in response.data
    assert appointment_status(app, appointment_id) == STATUS_CONFIRMED


def test_doctor_manages_working_hours(client, data):
    login(client, DOCTOR)
    added = client.post(
        "/doctor/availability",
        data={"weekday": "0", "start_time": "14:00", "end_time": "16:00", "slot_minutes": "20"},
        follow_redirects=True,
    )
    assert b"Working period added" in added.data
    overlap = client.post(
        "/doctor/availability",
        data={"weekday": "0", "start_time": "15:00", "end_time": "17:00", "slot_minutes": "20"},
        follow_redirects=True,
    )
    assert b"overlaps" in overlap.data


def test_admin_creates_a_doctor_who_can_then_log_in(app, client, data):
    login(client, ADMIN)
    created = client.post(
        "/admin/doctors/new",
        data={
            "name": "Rivera",
            "email": "rivera@example.com",
            "password": "doctor-pass-1",
            "specialization": "Dermatology",
            "department": "Skin Care",
        },
        follow_redirects=True,
    )
    assert b"Doctor account created" in created.data

    doctor_client = app.test_client()
    response = login(doctor_client, "rivera@example.com", "doctor-pass-1", follow_redirects=True)
    assert response.request.path == "/doctor/schedule"


def test_admin_can_deactivate_a_user(app, client, data):
    login(client, ADMIN)
    client.post(f"/admin/users/{data['alice_id']}/toggle")

    assert login(app.test_client(), ALICE).status_code == 401
    # Admins cannot lock themselves out.
    client.post(f"/admin/users/{data['admin_id']}/toggle")
    assert client.get("/admin/").status_code == 200


def test_notifications_page_lists_messages(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    page = client.get("/notifications")
    assert b"is confirmed" in page.data


# --- the redesigned pages -------------------------------------------------------------


def test_landing_page_has_a_preview_and_calls_to_action(client):
    page = client.get("/").data
    assert b"Book your doctor" in page
    assert b"Create an account" in page
    assert b"How booking works" in page


def test_doctor_list_shows_the_next_free_time_and_specialization_filters(client, data):
    login(client, ALICE)
    page = client.get("/patient/doctors").data
    assert b"Next free:" in page
    assert b'href="/patient/doctors?q=Cardiology"' in page

    empty = client.get("/patient/doctors?q=dermatology").data
    assert b"No doctors match" in empty


def test_doctor_page_shows_hours_date_strip_and_grouped_slots(client, data):
    login(client, ALICE)
    page = client.get(f"/patient/doctors/{data['doctor_id']}?date={tomorrow_at(9).date()}").data
    assert b"Working hours" in page
    assert b"Morning" in page
    assert b"Afternoon" not in page  # the seeded doctor stops at noon
    assert b"6 open" in page
    assert b"Choose a time to continue." in page


def test_date_strip_pages_forward_and_clamps_far_dates(client, data):
    login(client, ALICE)
    base = f"/patient/doctors/{data['doctor_id']}"
    later = client.get(f"{base}?date=2999-01-01")
    assert later.status_code == 200
    junk = client.get(f"{base}?date=not-a-date")
    assert junk.status_code == 200
    assert b"Earlier days" in client.get(f"{base}?date=2999-01-01").data


def test_a_day_without_slots_explains_why(app, client, data):
    from datetime import date, timedelta

    from app.extensions import db
    from app.models import Availability

    tomorrow = date.today() + timedelta(days=1)
    with app.app_context():
        db.session.query(Availability).filter_by(weekday=tomorrow.weekday()).delete()
        db.session.commit()
    login(client, ALICE)
    page = client.get(f"/patient/doctors/{data['doctor_id']}?date={tomorrow}").data
    assert b"No open times on this day" in page


def test_booked_appointments_render_as_stubs_with_actions(client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    page = client.get("/patient/appointments").data
    assert b'class="stub"' in page
    assert b"9:00 \xe2\x80\x93 9:30 AM" in page
    assert b"Reschedule" in page
    assert b"Cancel" in page


def test_empty_states_point_to_the_next_action(client, data):
    login(client, ALICE)
    assert b"No upcoming appointments" in client.get("/patient/appointments").data
    assert b"all caught up" in client.get("/notifications").data


def test_rescheduling_a_cancelled_appointment_is_refused_politely(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    appointment_id = only_appointment_id(app)
    client.post(f"/patient/appointments/{appointment_id}/cancel")

    response = client.get(
        f"/patient/appointments/{appointment_id}/reschedule", follow_redirects=True
    )
    assert b"Only confirmed appointments can be rescheduled" in response.data
    assert response.request.path == "/patient/appointments"


def test_reschedule_page_shows_the_current_booking(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    page = client.get(f"/patient/appointments/{only_appointment_id(app)}/reschedule").data
    assert b"Currently booked" in page
    assert b"Move appointment" in page


def test_doctor_timeline_shows_booked_and_open_slots(app, client, data):
    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))

    doctor_client = app.test_client()
    login(doctor_client, DOCTOR)
    page = doctor_client.get(f"/doctor/schedule?date={tomorrow_at(9).date()}").data
    assert b"1 booked, 5 open" in page
    assert b"Alice" in page
    assert b"Open" in page


def test_doctor_without_hours_on_a_day_gets_a_shortcut(app, client, data):
    from datetime import date

    from app.extensions import db
    from app.models import Availability

    day = date(2030, 1, 1)  # a Tuesday
    with app.app_context():
        db.session.query(Availability).filter_by(weekday=day.weekday()).delete()
        db.session.commit()
    login(client, DOCTOR)

    page = client.get(f"/doctor/schedule?date={day}").data
    assert b"No working hours on Tuesdays" in page
    assert b"Set working hours" in page
    assert b"booked," not in page


def test_working_hours_page_lists_every_weekday(client, data):
    login(client, DOCTOR)
    page = client.get("/doctor/availability").data
    for day in (b"Monday", b"Sunday"):
        assert day in page
    assert b"30 min visits" in page


def test_admin_dashboard_has_stats_and_filters(client, data):
    login(client, ADMIN)
    page = client.get("/admin/").get_data(as_text=True)
    assert "Upcoming appointments" in page
    assert 'data-role-filter="doctor"' in page
    # Seeded people: 1 admin, 1 doctor, 2 patients - each listed once in the table.
    # The signed-in admin's email also appears in the account menu, hence twice.
    for email in ("doctor@example.com", "alice@example.com", "bob@example.com"):
        assert page.count(email) == 1
    assert page.count("admin@example.com") == 2
    assert 'data-role="patient"' in page and 'data-role="doctor"' in page


def test_error_pages_use_the_site_layout(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert b"Page not found" in response.data
    assert b"Back to the home page" in response.data


def test_static_assets_are_served(client):
    for path, kind in [
        ("/static/style.css", "text/css"),
        ("/static/app.js", "javascript"),
        ("/static/fonts/figtree-latin-wght-normal.woff2", "font/woff2"),
        ("/static/fonts/bricolage-grotesque-latin-wght-normal.woff2", "font/woff2"),
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert kind in response.content_type, path


def test_pages_work_under_the_content_security_policy(app, client, data):
    """The CSP blocks inline styles and handlers, so no page may rely on them."""
    import re

    login(client, ALICE)
    book(client, data["doctor_id"], tomorrow_at(9))
    pages = [
        "/patient/doctors",
        f"/patient/doctors/{data['doctor_id']}",
        "/patient/appointments",
        f"/patient/appointments/{only_appointment_id(app)}/reschedule",
        "/notifications",
    ]
    doctor_client = app.test_client()
    login(doctor_client, DOCTOR)
    admin_client = app.test_client()
    login(admin_client, ADMIN)

    html = [client.get(p).get_data(as_text=True) for p in pages]
    html += [
        doctor_client.get(p).get_data(as_text=True)
        for p in ("/doctor/schedule", "/doctor/availability")
    ]
    html += [admin_client.get(p).get_data(as_text=True) for p in ("/admin/", "/admin/doctors/new")]
    html += [app.test_client().get(p).get_data(as_text=True) for p in ("/", "/login", "/register")]

    for page in html:
        assert not re.search(r"\sstyle=", page)
        assert not re.search(r"\son[a-z]+=", page)
        assert "<script>" not in page
    policy = client.get("/login").headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in policy and "form-action 'self'" in policy
