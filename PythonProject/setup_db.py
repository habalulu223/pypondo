# setup_db.py
from app import app, db, PC

# This enters the application context to access the database
with app.app_context():
    print("Creating database tables...")
    db.create_all()  # This creates the tables (User, PC, etc.)

    # Check if PCs exist, if not, create them
    if not PC.query.first():
        print("Adding default PCs...")
        for i in range(1, 6):
            db.session.add(PC(name=f'PC-{i}'))
        db.session.commit()
        print("Default PCs added.")
    else:
        print("PCs already exist.")

    print("Database setup complete!")