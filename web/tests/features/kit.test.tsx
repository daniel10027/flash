import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { useState } from 'react';
import { AmountField, ConfirmSheet, PageHeader, Receipt } from '@features/common/kit';

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  // eslint-disable-next-line @typescript-eslint/consistent-type-imports
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});

function inRouter(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('PageHeader', () => {
  it('affiche le titre et le sous-titre', () => {
    inRouter(<PageHeader title="Envoyer" subtitle="vers un numéro" />);
    expect(screen.getByRole('heading', { name: 'Envoyer' })).toBeInTheDocument();
    expect(screen.getByText('vers un numéro')).toBeInTheDocument();
  });

  it('le bouton retour appelle navigate(-1) et disparaît si back=false', async () => {
    const { rerender } = inRouter(<PageHeader title="X" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retour' }));
    expect(navigate).toHaveBeenCalledWith(-1);
    rerender(
      <MemoryRouter>
        <PageHeader title="X" back={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button', { name: 'Retour' })).not.toBeInTheDocument();
  });
});

describe('AmountField', () => {
  function Harness({ currency }: { currency: string }) {
    const [v, setV] = useState(0);
    return (
      <>
        <AmountField currency={currency} value={v} onChange={setV} showFee />
        <output data-testid="minor">{v}</output>
      </>
    );
  }

  it('XOF : saisie sans décimale, frais 0,8 % arrondis au supérieur', () => {
    render(<Harness currency="XOF" />);
    fireEvent.change(screen.getByLabelText('Montant'), { target: { value: '10000' } });
    expect(screen.getByTestId('minor')).toHaveTextContent('10000');
    // frais = ceil(10000 * 80 / 10000) = 80 ; total débité = 10 080
    expect(screen.getByText(/Frais \(0,8 %\)/)).toBeInTheDocument();
    expect(screen.getByText('Total débité')).toBeInTheDocument();
    expect(screen.getByText((t) => t.replace(/\D/g, '') === '10080')).toBeInTheDocument();
  });

  it('devise à 2 décimales : la valeur est convertie en minor', () => {
    render(<Harness currency="EUR" />);
    fireEvent.change(screen.getByLabelText('Montant'), { target: { value: '12.50' } });
    expect(screen.getByTestId('minor')).toHaveTextContent('1250');
  });

  it('sans montant, aucun encart de frais', () => {
    render(<AmountField currency="XOF" value={0} onChange={() => {}} showFee />);
    expect(screen.queryByText(/Frais/)).not.toBeInTheDocument();
  });
});

describe('ConfirmSheet', () => {
  it('le bouton Confirmer reste désactivé sous 4 chiffres', async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmSheet
        open
        onClose={() => {}}
        onConfirm={onConfirm}
        title="Confirmer l’envoi"
        summary={<p>résumé</p>}
      />,
    );
    const btn = screen.getByRole('button', { name: 'Confirmer' });
    expect(btn).toBeDisabled();
    for (const [i, d] of [...'1397'].entries()) {
      await userEvent.type(screen.getByLabelText(`Chiffre ${i + 1}`), d);
    }
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    expect(onConfirm).toHaveBeenCalled();
  });
});

describe('Receipt', () => {
  it('rend les champs scalaires et ignore objets / null', () => {
    render(<Receipt data={{ montant_minor: 10000, statut: 'OK', meta: { x: 1 }, note: null }} />);
    expect(screen.getByText('montant minor')).toBeInTheDocument();
    expect(screen.getByText('10000')).toBeInTheDocument();
    expect(screen.getByText('statut')).toBeInTheDocument();
    expect(screen.queryByText('meta')).not.toBeInTheDocument();
    expect(screen.queryByText('note')).not.toBeInTheDocument();
  });
});
