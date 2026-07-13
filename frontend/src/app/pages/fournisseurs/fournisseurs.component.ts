import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription, interval, switchMap } from 'rxjs';
import { ApiService, Fournisseur, SynchroCatalogue } from '../../core/api.service';

@Component({
  selector: 'app-fournisseurs',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './fournisseurs.component.html',
  styleUrl: './fournisseurs.component.scss',
})
export class FournisseursComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);

  items = signal<Fournisseur[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  editing = signal<Fournisseur | null>(null);

  // Suivi du robot : une synchro dure plusieurs minutes, on interroge le serveur.
  synchro = signal<SynchroCatalogue | null>(null);
  showSynchroModal = signal(false);
  private sondage?: Subscription;

  // Aide « récupérer la session du navigateur »
  showAideSession = signal(false);
  snippetCopie = signal(false);

  /** Snippet à exécuter dans la console (F12) du site fournisseur, magasin déjà choisi.
   *  Validé de bout en bout : sa sortie est rechargée telle quelle par le robot.
   *  Volontairement basé sur `document.cookie` — les cookies HttpOnly ne sont pas
   *  nécessaires au choix du magasin, et sont de toute façon inaccessibles au script. */
  readonly snippetSession = `copy(JSON.stringify({
  cookies: document.cookie.split('; ').filter(Boolean).map(c => {
    const i = c.indexOf('=');
    return { name: c.slice(0, i), value: c.slice(i + 1),
             domain: location.hostname, path: '/', expires: -1,
             httpOnly: false, secure: true, sameSite: 'Lax' };
  }),
  origins: [{ origin: location.origin,
    localStorage: Object.entries(localStorage).map(([name, value]) => ({ name, value })) }]
}))`;

  form: Fournisseur = this.formulaireVide();

  private formulaireVide(): Fournisseur {
    return {
      nom: '', email: '', telephone: '', commentaire: '',
      url: '', identifiant: '', mot_de_passe: '', rattachement_auto: true,
      code_postal: '', session_state: '',
    };
  }

  ngOnInit(): void { this.load(); }

  ngOnDestroy(): void { this.sondage?.unsubscribe(); }

  load(): void {
    this.loading.set(true);
    this.api.getFournisseurs().subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = this.formulaireVide();
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Fournisseur): void {
    // Ni le mot de passe ni la session ne sont renvoyés par l'API : champs vides,
    // et un champ vide signifie « ne change rien ».
    this.form = { ...item, mot_de_passe: '', session_state: '' };
    this.editing.set(item);
    this.showModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updateFournisseur(id, this.form)
      : this.api.createFournisseur(this.form);
    obs.subscribe({
      next: () => { this.showModal.set(false); this.load(); },
      error: err => this.error.set(`Erreur enregistrement : ${err.status}`),
    });
  }

  delete(item: Fournisseur): void {
    if (!confirm(`Supprimer "${item.nom}" ?`)) return;
    this.api.deleteFournisseur(item.id!).subscribe({ next: () => this.load() });
  }

  // ----- Robot de catalogue -----

  lancerRobot(item: Fournisseur): void {
    if (!item.id) return;
    this.error.set(null);
    this.api.synchroniserFournisseur(item.id).subscribe({
      next: synchro => {
        this.synchro.set(synchro);
        this.showSynchroModal.set(true);
        this.suivre(synchro.id!);
      },
      error: err => {
        if (err.status === 409) {
          // Une synchro tourne déjà : on se raccroche à celle-là plutôt que d'en lancer une 2e.
          const encours = err.error?.synchro as SynchroCatalogue | undefined;
          if (encours?.id) {
            this.synchro.set(encours);
            this.showSynchroModal.set(true);
            this.suivre(encours.id);
            return;
          }
        }
        this.error.set(err.error?.detail ?? `Erreur lancement du robot : ${err.status}`);
      },
    });
  }

  /** Interroge le serveur toutes les 2 s jusqu'à la fin du run. */
  private suivre(synchroId: number): void {
    this.sondage?.unsubscribe();
    this.sondage = interval(2000)
      .pipe(switchMap(() => this.api.getSynchro(synchroId)))
      .subscribe({
        next: s => {
          this.synchro.set(s);
          if (s.statut !== 'en_cours') {
            this.sondage?.unsubscribe();
            this.load();   // rafraîchit les compteurs
          }
        },
        error: () => this.sondage?.unsubscribe(),
      });
  }

  oublierSession(item: Fournisseur): void {
    if (!item.id) return;
    if (!confirm(
      `Oublier la session mémorisée pour "${item.nom}" ?\n\n` +
      'Magasin choisi, cookies acceptés et connexion seront perdus : la prochaine ' +
      'synchronisation repartira d\'un navigateur vierge.'
    )) return;
    this.api.oublierSession(item.id).subscribe({
      next: () => this.load(),
      error: err => this.error.set(`Erreur : ${err.status}`),
    });
  }

  oublierSelecteurs(item: Fournisseur): void {
    if (!item.id) return;
    if (!confirm(
      `Oublier les XPath mémorisés pour "${item.nom}" ?\n\n` +
      'La prochaine synchronisation redécouvrira le site via Mistral ' +
      '(plus lent et plus coûteux, mais utile si le site a changé).'
    )) return;
    this.api.oublierSelecteurs(item.id).subscribe({
      next: () => this.error.set(null),
      error: err => this.error.set(`Erreur : ${err.status}`),
    });
  }

  copierSnippet(): void {
    navigator.clipboard.writeText(this.snippetSession).then(() => {
      this.snippetCopie.set(true);
      setTimeout(() => this.snippetCopie.set(false), 2500);
    });
  }

  fermerSynchro(): void {
    this.sondage?.unsubscribe();
    this.showSynchroModal.set(false);
  }

  close(): void { this.showModal.set(false); }
}
