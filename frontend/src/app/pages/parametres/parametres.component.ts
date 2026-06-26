import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ApiService, ConfigurationStripe, ConfigurationEmail } from '../../core/api.service';

interface EnvWindow { __env?: { apiUrl?: string }; }

@Component({
  selector: 'app-parametres',
  standalone: true,
  imports: [FormsModule, DatePipe],
  templateUrl: './parametres.component.html',
  styleUrl: './parametres.component.scss',
})
export class ParametresComponent implements OnInit {
  private api = inject(ApiService);

  loading = signal(true);

  // ── Stripe ──
  stripeForm: ConfigurationStripe = { stripe_secret_key: '', stripe_webhook_secret: '' };
  stripeUpdatedAt = signal<string | null>(null);
  stripeSaving = signal(false);
  stripeError = signal<string | null>(null);
  stripeSuccess = signal<string | null>(null);
  showKey = signal(false);
  showWebhook = signal(false);

  // ── Email / SMTP ──
  emailForm: ConfigurationEmail = {
    actif: false, email_host: '', email_port: 587, email_use_tls: true,
    email_host_user: '', email_host_password: '', default_from_email: '',
  };
  emailUpdatedAt = signal<string | null>(null);
  emailSaving = signal(false);
  emailError = signal<string | null>(null);
  emailSuccess = signal<string | null>(null);
  showPwd = signal(false);
  testDest = '';
  testLoading = signal(false);
  testResult = signal<string | null>(null);
  testError = signal<string | null>(null);

  get webhookUrl(): string {
    const base = (window as unknown as EnvWindow).__env?.apiUrl ?? '';
    return `${base}/api/stripe/webhook/`;
  }

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getConfigurationStripe().subscribe({
      next: c => {
        this.stripeForm = { stripe_secret_key: c.stripe_secret_key, stripe_webhook_secret: c.stripe_webhook_secret };
        this.stripeUpdatedAt.set(c.updated_at ?? null);
      },
    });
    this.api.getConfigurationEmail().subscribe({
      next: c => { this.emailForm = { ...c }; this.emailUpdatedAt.set(c.updated_at ?? null); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  saveStripe(): void {
    this.stripeSaving.set(true);
    this.stripeError.set(null);
    this.stripeSuccess.set(null);
    this.api.updateConfigurationStripe(this.stripeForm).subscribe({
      next: c => {
        this.stripeForm = { stripe_secret_key: c.stripe_secret_key, stripe_webhook_secret: c.stripe_webhook_secret };
        this.stripeUpdatedAt.set(c.updated_at ?? null);
        this.stripeSaving.set(false);
        this.stripeSuccess.set('Configuration Stripe enregistrée.');
        setTimeout(() => this.stripeSuccess.set(null), 4000);
      },
      error: err => { this.stripeError.set(`Erreur lors de la sauvegarde (${err.status})`); this.stripeSaving.set(false); },
    });
  }

  saveEmail(): void {
    this.emailSaving.set(true);
    this.emailError.set(null);
    this.emailSuccess.set(null);
    this.api.updateConfigurationEmail(this.emailForm).subscribe({
      next: c => {
        this.emailForm = { ...c };
        this.emailUpdatedAt.set(c.updated_at ?? null);
        this.emailSaving.set(false);
        this.emailSuccess.set('Configuration email enregistrée.');
        setTimeout(() => this.emailSuccess.set(null), 4000);
      },
      error: err => { this.emailError.set(`Erreur lors de la sauvegarde (${err.status})`); this.emailSaving.set(false); },
    });
  }

  envoyerTest(): void {
    if (!this.testDest) return;
    this.testLoading.set(true);
    this.testResult.set(null);
    this.testError.set(null);
    this.api.testEmail(this.testDest).subscribe({
      next: r => { this.testResult.set(r.detail); this.testLoading.set(false); },
      error: err => { this.testError.set(err.error?.detail ?? `Erreur ${err.status}`); this.testLoading.set(false); },
    });
  }
}
