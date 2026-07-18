import { Component, ElementRef, HostListener, inject, signal, ViewChild } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive, Router, NavigationEnd } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map, startWith } from 'rxjs';
import { KeycloakService } from './core/keycloak.service';
import { ThemeService } from './core/theme.service';

type NavEntry =
  | { kind: 'section'; label: string }
  | { kind: 'link'; label: string; abbr: string; path: string; exact?: boolean; managerOnly?: boolean };

const MOBILE_CLOSE_ANIM_MS = 220;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgTemplateOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class AppComponent {
  private router = inject(Router);
  protected kc = inject(KeycloakService);
  protected theme = inject(ThemeService);

  isPublic = toSignal(
    this.router.events.pipe(
      filter(e => e instanceof NavigationEnd),
      map((e: NavigationEnd) => e.urlAfterRedirects.startsWith('/commander')),
      startWith(window.location.pathname.includes('/commander')),
    ),
    { initialValue: window.location.pathname.includes('/commander') },
  );

  collapsed = signal(false);
  mobileOpen = signal(false);
  mobileClosing = signal(false);

  protected noop = (): void => {};
  protected closeMobileFn = (): void => this.closeMobile();

  private readonly allNavEntries: NavEntry[] = [
    { kind: 'link', path: '/', label: 'Tableau de bord', abbr: 'Tb', exact: true },
    { kind: 'section', label: 'Cuisine' },
    { kind: 'link', path: '/ingredients', label: 'Ingrédients', abbr: 'In' },
    { kind: 'link', path: '/recettes', label: 'Recettes', abbr: 'Re' },
    { kind: 'link', path: '/plats', label: 'Plats', abbr: 'Pl' },
    { kind: 'link', path: '/categories-plat', label: 'Catégories', abbr: 'Ct', managerOnly: true },
    { kind: 'section', label: 'Service' },
    { kind: 'link', path: '/plan-tables', label: 'Plan des tables', abbr: 'Pt' },
    { kind: 'link', path: '/commandes', label: 'Commandes', abbr: 'Cm' },
    { kind: 'section', label: 'Administration' },
    { kind: 'link', path: '/fournisseurs', label: 'Fournisseurs', abbr: 'Fo' },
    { kind: 'link', path: '/planning', label: 'Planning', abbr: 'Pn' },
    { kind: 'link', path: '/unites', label: 'Unités', abbr: 'Un' },
    { kind: 'link', path: '/utilisateurs', label: 'Utilisateurs', abbr: 'Ut', managerOnly: true },
    { kind: 'link', path: '/parametres', label: 'Paramétrage', abbr: 'Pa', managerOnly: true },
    { kind: 'section', label: 'Analyse économique' },
    { kind: 'link', path: '/analyse/evenements', label: 'Événements', abbr: 'Ev', managerOnly: true },
    { kind: 'link', path: '/analyse/meteo', label: 'Météo', abbr: 'Mt', managerOnly: true },
    { kind: 'link', path: '/analyse/ventes', label: 'Ventes', abbr: 'Ve', managerOnly: true },
    { kind: 'link', path: '/analyse/regression', label: 'Régression', abbr: 'Rg', managerOnly: true },
  ];

  get navEntries(): NavEntry[] {
    const isManager = this.kc.isManager();
    return this.allNavEntries.filter(e => e.kind === 'section' || !e.managerOnly || isManager);
  }

  @ViewChild('closeBtn') private closeBtnRef?: ElementRef<HTMLButtonElement>;
  @ViewChild('burgerBtn') private burgerBtnRef?: ElementRef<HTMLButtonElement>;

  toggleCollapsed(): void {
    this.collapsed.update(v => !v);
  }

  openMobile(): void {
    this.mobileOpen.set(true);
    this.mobileClosing.set(false);
    document.body.style.overflow = 'hidden';
    setTimeout(() => this.closeBtnRef?.nativeElement.focus());
  }

  closeMobile(): void {
    if (!this.mobileOpen() || this.mobileClosing()) return;
    this.mobileClosing.set(true);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setTimeout(() => {
      this.mobileOpen.set(false);
      this.mobileClosing.set(false);
      document.body.style.overflow = '';
      this.burgerBtnRef?.nativeElement.focus();
    }, reduced ? 0 : MOBILE_CLOSE_ANIM_MS);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.mobileOpen()) this.closeMobile();
  }

  get username(): string {
    return this.kc.username || this.kc.email;
  }

  get role(): string {
    const g = this.kc.groups;
    if (g.includes('manager')) return 'Manager';
    if (g.includes('cuisinier')) return 'Cuisinier';
    if (g.includes('serveur')) return 'Serveur';
    return '';
  }

  logout(): void {
    this.kc.logout();
  }
}

export { AppComponent as App };
