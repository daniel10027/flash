import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button, PinInput } from '@shared/ui';

describe('Button', () => {
  it('bloque le clic quand loading', async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Envoyer
      </Button>,
    );
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
  });
});

describe('PinInput', () => {
  it('avance le focus et ne garde que les chiffres', async () => {
    const user = userEvent.setup();
    let value = '';
    const onChange = vi.fn((v: string) => (value = v));
    render(<PinInput value="" onChange={onChange} label="Code" />);
    const inputs = screen.getAllByLabelText(/Chiffre/);
    await user.type(inputs[0]!, 'a1');
    expect(onChange).toHaveBeenCalled();
    expect(value).toBe('1');
  });
});
