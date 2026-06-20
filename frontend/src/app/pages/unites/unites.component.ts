import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Unite } from '../../core/api.service';

@Component({
  selector: 'app-unites',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './unites.component.html',
  styleUrl: './unites.component.scss',
})
export class UnitesComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Unite[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  editing = signal<Unite | null>(null);

  form: Unite = { nom: '', description: '' };

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getUnites().subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { nom: '', description: '' };
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Unite): void {
    this.form = { ...item };
    this.editing.set(item);
    this.showModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updateUnite(id, this.form)
      : this.api.createUnite(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  delete(item: Unite): void {
    if (!confirm(`Supprimer l'unité "${item.nom}" ?`)) return;
    this.api.deleteUnite(item.id!).subscribe({ next: () => this.load() });
  }

  close(): void { this.showModal.set(false); }
}
