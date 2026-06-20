import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ApiService, PlageTravail, Employe } from '../../core/api.service';

@Component({
  selector: 'app-planning',
  standalone: true,
  imports: [FormsModule, DatePipe],
  templateUrl: './planning.component.html',
  styleUrl: './planning.component.scss',
})
export class PlanningComponent implements OnInit {
  private api = inject(ApiService);

  plages = signal<PlageTravail[]>([]);
  employes = signal<Employe[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  editing = signal<PlageTravail | null>(null);
  filterEmployeId: number | '' = '';

  form: Partial<PlageTravail> = {};

  ngOnInit(): void {
    this.load();
    this.api.getEmployes().subscribe({ next: e => this.employes.set(e) });
  }

  load(): void {
    this.loading.set(true);
    this.api.getPlagesTravail(this.filterEmployeId || undefined).subscribe({
      next: items => { this.plages.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { employe: undefined, debut: '', fin: '', note: '' };
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: PlageTravail): void {
    this.form = { ...item };
    this.editing.set(item);
    this.showModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updatePlageTravail(id, this.form)
      : this.api.createPlageTravail(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  delete(item: PlageTravail): void {
    if (!confirm('Supprimer cette plage de travail ?')) return;
    this.api.deletePlageTravail(item.id!).subscribe({ next: () => this.load() });
  }

  duration(p: PlageTravail): string {
    const diff = new Date(p.fin).getTime() - new Date(p.debut).getTime();
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    return `${h}h${m.toString().padStart(2, '0')}`;
  }

  close(): void { this.showModal.set(false); }
}
