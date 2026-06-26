from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_table_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigurationStripe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stripe_secret_key', models.CharField(blank=True, default='', max_length=255)),
                ('stripe_webhook_secret', models.CharField(blank=True, default='', max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'configuration_stripe',
            },
        ),
    ]
