import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ApiService, Utilisateur } from '../../core/api.service';

const ROLES = ['manager', 'cuisinier', 'serveur'];

@Component({
  selector: 'app-utilisateurs',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './utilisateurs.component.html',
  styleUrl: './utilisateurs.component.scss',
})
export class UtilisateursComponent implements OnInit {
  private api = inject(ApiService);
  readonly roles = ROLES;

  items = signal<Utilisateur[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  message = signal<string | null>(null);

  showModal = signal(false);
  editing = signal<Utilisateur | null>(null);
  saving = signal(false);
  modalError = signal<string | null>(null);
  form: { email: string; prenom: string; nom: string; roles: string[] } =
    { email: '', prenom: '', nom: '', roles: [] };

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getUtilisateurs().subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(this.msg(err)); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { email: '', prenom: '', nom: '', roles: [] };
    this.editing.set(null);
    this.modalError.set(null);
    this.showModal.set(true);
  }

  openEditRoles(u: Utilisateur): void {
    this.form = { email: u.email, prenom: u.prenom, nom: u.nom, roles: [...u.roles] };
    this.editing.set(u);
    this.modalError.set(null);
    this.showModal.set(true);
  }

  hasRole(role: string): boolean { return this.form.roles.includes(role); }

  toggleRole(role: string): void {
    const i = this.form.roles.indexOf(role);
    if (i >= 0) this.form.roles.splice(i, 1); else this.form.roles.push(role);
  }

  save(): void {
    this.modalError.set(null);
    if (this.form.roles.length === 0) { this.modalError.set('Sélectionnez au moins un rôle.'); return; }
    this.saving.set(true);
    const u = this.editing();
    if (u) {
      this.api.updateRolesUtilisateur(u.id!, this.form.roles).subscribe({
        next: () => { this.afterSave('Rôles mis à jour.'); },
        error: err => { this.saving.set(false); this.modalError.set(this.msg(err)); },
      });
    } else {
      this.api.createUtilisateur(this.form).subscribe({
        next: created => this.afterSave(created.invitation_envoyee
          ? `Utilisateur créé — invitation envoyée à ${created.email}.`
          : `Utilisateur créé, mais l'email n'a pas pu être envoyé. Utilisez « Renvoyer l'invitation ».`),
        error: err => { this.saving.set(false); this.modalError.set(this.msg(err)); },
      });
    }
  }

  resend(u: Utilisateur): void {
    this.error.set(null);
    this.api.inviterUtilisateur(u.id!).subscribe({
      next: r => this.message.set(r.detail),
      error: err => this.error.set(this.msg(err)),
    });
  }

  toggleEtat(u: Utilisateur): void {
    this.api.setEtatUtilisateur(u.id!, !(u.enabled !== false)).subscribe({
      next: () => this.load(),
      error: err => this.error.set(this.msg(err)),
    });
  }

  close(): void { this.showModal.set(false); }

  private afterSave(message: string): void {
    this.saving.set(false);
    this.showModal.set(false);
    this.message.set(message);
    this.load();
  }

  private msg(err: HttpErrorResponse): string {
    return (err?.error?.detail as string) ?? `Erreur ${err?.status ?? ''}`.trim();
  }
}
