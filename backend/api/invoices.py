"""Génération locale (gratuite) du PDF de facture + envoi par email.

Aucune dépendance Stripe : on produit nous-mêmes le PDF avec ReportLab.
"""
import io
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.mail import EmailMessage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .models import Paiement

_VERT = colors.HexColor('#2e7d32')


def montants_ht_tva_ttc(facture):
    """Décompose le TTC en HT + TVA (prix des plats considérés TTC)."""
    ttc = Decimal(facture.montant_ttc)
    taux = Decimal(facture.taux_tva)
    ht = (ttc / (1 + taux / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tva = (ttc - ht).quantize(Decimal('0.01'))
    return ht, tva, ttc


def generer_pdf_facture(facture) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    titre = ParagraphStyle('titre', parent=styles['Title'], fontSize=18, textColor=_VERT)
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, textColor=colors.grey)
    elems = []

    # En-tête restaurant
    elems.append(Paragraph(getattr(settings, 'RESTO_NOM', 'Restaurant'), titre))
    infos = []
    if getattr(settings, 'RESTO_ADRESSE', ''):
        infos.append(settings.RESTO_ADRESSE)
    if getattr(settings, 'RESTO_SIRET', ''):
        infos.append(f'SIRET : {settings.RESTO_SIRET}')
    if getattr(settings, 'RESTO_TVA_INTRA', ''):
        infos.append(f'TVA intracom. : {settings.RESTO_TVA_INTRA}')
    if infos:
        elems.append(Paragraph('<br/>'.join(infos), small))
    elems.append(Spacer(1, 8 * mm))

    # Référence facture
    commande = facture.commande
    elems.append(Paragraph(f'Facture {facture.numero}', styles['Heading2']))
    meta = f'Date : {facture.created_at:%d/%m/%Y}'
    if commande.numero_table:
        meta += f' · Table {commande.numero_table}'
    meta += f' · Commande #{commande.pk}'
    elems.append(Paragraph(meta, normal))
    elems.append(Spacer(1, 6 * mm))

    # Lignes de commande
    data = [['Désignation', 'Qté', 'P.U. TTC', 'Total TTC']]
    for ligne in commande.lignes_commande.all():
        pu = Decimal(ligne.prix_unitaire_snapshot)
        data.append([
            ligne.plat.nom, str(ligne.quantite),
            f'{pu:.2f} €', f'{pu * ligne.quantite:.2f} €',
        ])
    table = Table(data, colWidths=[90 * mm, 20 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _VERT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elems.append(table)
    elems.append(Spacer(1, 6 * mm))

    # Totaux
    ht, tva, ttc = montants_ht_tva_ttc(facture)
    totaux = Table(
        [
            ['Total HT', f'{ht:.2f} €'],
            [f'TVA ({facture.taux_tva:.1f} %)', f'{tva:.2f} €'],
            ['Total TTC', f'{ttc:.2f} €'],
        ],
        colWidths=[140 * mm, 30 * mm], hAlign='RIGHT',
    )
    totaux.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elems.append(totaux)

    # Règlement
    elems.append(Spacer(1, 8 * mm))
    paiement = Paiement.objects.filter(commande=commande).select_related('statut').first()
    if paiement:
        etat = 'payé' if paiement.statut.nom == 'paye' else 'en attente de règlement'
        elems.append(Paragraph(f'Règlement : {paiement.methode} — {etat}', normal))

    elems.append(Spacer(1, 10 * mm))
    elems.append(Paragraph('Merci de votre visite.', small))

    doc.build(elems)
    return buffer.getvalue()


def envoyer_facture_email(facture, pdf_bytes, destinataire):
    resto = getattr(settings, 'RESTO_NOM', '')
    message = EmailMessage(
        subject=f'Votre facture {facture.numero}',
        body=(
            f'Bonjour,\n\nVeuillez trouver ci-joint votre facture {facture.numero} '
            f"d'un montant de {facture.montant_ttc:.2f} € TTC.\n\n{resto}"
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        to=[destinataire],
    )
    message.attach(f'{facture.numero}.pdf', pdf_bytes, 'application/pdf')
    message.send(fail_silently=False)
