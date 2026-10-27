from django.db import migrations


class Migration(migrations.Migration):
    """Drop the old Project (integer key, other status set).

    The data is test data; the new Project is created in the next migration.
    """

    dependencies = [
        ('projects', '0003_add_project_status'),
        ('dashboard', '0004_delete_savedproject'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Project',
        ),
    ]
