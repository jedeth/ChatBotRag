# Generated manually on 2026-02-06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rag', '0002_documentchunk_hnsw_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
