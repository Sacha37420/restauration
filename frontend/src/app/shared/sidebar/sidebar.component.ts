import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { KeycloakService } from '../../core/keycloak.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss',
})
export class SidebarComponent {
  private kc = inject(KeycloakService);

  get username(): string { return this.kc.username || this.kc.email; }
  get role(): string {
    const g = this.kc.groups;
    if (g.includes('manager')) return 'Manager';
    if (g.includes('cuisinier')) return 'Cuisinier';
    if (g.includes('serveur')) return 'Serveur';
    return '';
  }

  logout(): void { this.kc.logout(); }
}
