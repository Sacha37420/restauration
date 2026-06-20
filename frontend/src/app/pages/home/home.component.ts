import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { KeycloakService } from '../../core/keycloak.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent implements OnInit {
  private api = inject(ApiService);
  private kc = inject(KeycloakService);

  username = this.kc.username;
  role = (() => {
    const g = this.kc.groups;
    if (g.includes('manager')) return 'Manager';
    if (g.includes('cuisinier')) return 'Cuisinier';
    if (g.includes('serveur')) return 'Serveur';
    return '';
  })();

  nbIngredients = signal(0);
  nbAlertes = signal(0);
  nbCommandes = signal(0);
  nbPlats = signal(0);

  ngOnInit(): void {
    this.api.getIngredients().subscribe({ next: items => this.nbIngredients.set(items.length) });
    this.api.getIngredients(true).subscribe({ next: items => this.nbAlertes.set(items.length) });
    this.api.getCommandes().subscribe({ next: items => this.nbCommandes.set(items.length) });
    this.api.getPlats({ actif: true }).subscribe({ next: items => this.nbPlats.set(items.length) });
  }
}
