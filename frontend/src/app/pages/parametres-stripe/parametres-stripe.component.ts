import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ApiService, ConfigurationStripe } from '../../core/api.service';

@Component({
  selector: 'app-parametres-stripe',
  standalone: true,
  imports: [FormsModule, DatePipe],
  templateUrl: './parametres-stripe.component.html',
  styleUrl: './parametres-stripe.component.scss',
})
export class ParametresStripeComponent implements OnInit {
  private api = inject(ApiService);

  loading = signal(true);
  saving = signal(false);
  error = signal<string | null>(null);
  success = signal<string | null>(null);

  form: ConfigurationStripe = { stripe_secret_key: '', stripe_webhook_secret: '' };
  updated_at = signal<string | null>(null);

  // Contrôle de visibilité des champs
  showKey = signal(false);
  showWebhook = signal(false);

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getConfigurationStripe().subscribe({
      next: config => {
        this.form = { stripe_secret_key: config.stripe_secret_key, stripe_webhook_secret: config.stripe_webhook_secret };
        this.updated_at.set(config.updated_at ?? null);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(`Impossible de charger la configuration (${err.status})`);
        this.loading.set(false);
      },
    });
  }

  save(): void {
    this.saving.set(true);
    this.error.set(null);
    this.success.set(null);
    this.api.updateConfigurationStripe(this.form).subscribe({
      next: config => {
        this.form = { stripe_secret_key: config.stripe_secret_key, stripe_webhook_secret: config.stripe_webhook_secret };
        this.updated_at.set(config.updated_at ?? null);
        this.saving.set(false);
        this.success.set('Configuration Stripe enregistrée.');
        setTimeout(() => this.success.set(null), 4000);
      },
      error: err => {
        this.error.set(`Erreur lors de la sauvegarde (${err.status})`);
        this.saving.set(false);
      },
    });
  }
}
