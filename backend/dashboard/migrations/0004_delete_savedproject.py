from django.db import migrations


class Migration(migrations.Migration):
    """Drop SavedProject so projects.Project can be recreated with a UUID key.

    The data is test data; the table is created again after the new Project.
    """

    dependencies = [
        ('dashboard', '0003_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SavedProject',
        ),
    ]
