import click

from .demo import DemoDataExistsError, seed_demo
from .extensions import db
from .models import ROLE_ADMIN, User
from .security import is_valid_email


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(name, email, password):
        """Create an administrator account (password is prompted, never stored in code)."""
        email = email.strip().lower()
        if not is_valid_email(email):
            raise click.ClickException("That is not a valid email address.")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        if db.session.query(User).filter_by(email=email).first():
            raise click.ClickException("A user with that email already exists.")
        admin = User(name=name.strip(), email=email, role=ROLE_ADMIN)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Administrator {email} created.")

    @app.cli.command("seed-demo")
    @click.password_option(help="Password shared by every demo account.")
    def seed_demo_command(password):
        """Add sample doctors, patients and bookings (for trying the app out locally)."""
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        db.create_all()
        try:
            accounts = seed_demo(password)
        except DemoDataExistsError as error:
            raise click.ClickException(
                f"{error} Delete the database file and run init-db again to start fresh."
            ) from None
        click.echo("Demo data created. Log in with any of these emails and the password you chose:")
        for role, name, email in accounts:
            click.echo(f"  {role:<8} {email:<28} {name}")
        click.echo("Do not run seed-demo on a real or public deployment.")
