import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import {
  ApiService, ConfigurationStripe, ConfigurationEmail,
  ConfigurationAgentEvenements, ConfigurationMeteo,
} from '../../core/api.service';

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

  // ── Agent calendrier d'événements (IA) ──
  agentForm: ConfigurationAgentEvenements = {
    actif: false, mistral_api_key: '', modele: 'mistral-large-latest', system_prompt: '',
    ville: '', mois: null, annee: null,
  };
  agentUpdatedAt = signal<string | null>(null);
  agentSaving = signal(false);
  agentError = signal<string | null>(null);
  agentSuccess = signal<string | null>(null);
  showAgentKey = signal(false);

  // ── Météo-France ──
  meteoForm: ConfigurationMeteo = {
    actif: false, api_key: '', ville: '', mois: null, annee: null,
  };
  meteoUpdatedAt = signal<string | null>(null);
  meteoSaving = signal(false);
  meteoError = signal<string | null>(null);
  meteoSuccess = signal<string | null>(null);
  showMeteoKey = signal(false);

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
    this.api.getConfigurationAgent().subscribe({
      next: c => { this.agentForm = { ...c }; this.agentUpdatedAt.set(c.updated_at ?? null); },
    });
    this.api.getConfigurationMeteo().subscribe({
      next: c => { this.meteoForm = { ...c }; this.meteoUpdatedAt.set(c.updated_at ?? null); },
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

  saveAgent(): void {
    this.agentSaving.set(true);
    this.agentError.set(null);
    this.agentSuccess.set(null);
    this.api.updateConfigurationAgent(this.agentForm).subscribe({
      next: c => {
        this.agentForm = { ...c };
        this.agentUpdatedAt.set(c.updated_at ?? null);
        this.agentSaving.set(false);
        this.agentSuccess.set('Configuration agent enregistrée.');
        setTimeout(() => this.agentSuccess.set(null), 4000);
      },
      error: err => { this.agentError.set(`Erreur lors de la sauvegarde (${err.status})`); this.agentSaving.set(false); },
    });
  }

  saveMeteo(): void {
    this.meteoSaving.set(true);
    this.meteoError.set(null);
    this.meteoSuccess.set(null);
    this.api.updateConfigurationMeteo(this.meteoForm).subscribe({
      next: c => {
        this.meteoForm = { ...c };
        this.meteoUpdatedAt.set(c.updated_at ?? null);
        this.meteoSaving.set(false);
        this.meteoSuccess.set('Configuration météo enregistrée.');
        setTimeout(() => this.meteoSuccess.set(null), 4000);
      },
      error: err => { this.meteoError.set(`Erreur lors de la sauvegarde (${err.status})`); this.meteoSaving.set(false); },
    });
  }
}
