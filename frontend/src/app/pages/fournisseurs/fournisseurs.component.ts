import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Fournisseur } from '../../core/api.service';

@Component({
  selector: 'app-fournisseurs',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './fournisseurs.component.html',
  styleUrl: './fournisseurs.component.scss',
})
export class FournisseursComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Fournisseur[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  editing = signal<Fournisseur | null>(null);

  form: Fournisseur = { nom: '', email: '', telephone: '', commentaire: '' };

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getFournisseurs().subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { nom: '', email: '', telephone: '', commentaire: '' };
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Fournisseur): void {
    this.form = { ...item };
    this.editing.set(item);
    this.showModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updateFournisseur(id, this.form)
      : this.api.createFournisseur(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  delete(item: Fournisseur): void {
    if (!confirm(`Supprimer "${item.nom}" ?`)) return;
    this.api.deleteFournisseur(item.id!).subscribe({ next: () => this.load() });
  }

  close(): void { this.showModal.set(false); }
}
