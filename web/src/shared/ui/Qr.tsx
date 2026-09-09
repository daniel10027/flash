// WEB-019 — rendu d'un QR à partir d'une charge utile texte.
import { useEffect, useRef } from 'react';
import QRCode from 'qrcode';

export function Qr({ value, size = 220 }: { value: string; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    void QRCode.toCanvas(ref.current, value, {
      width: size,
      margin: 1,
      color: { dark: '#161619', light: '#ffffff' },
    });
  }, [value, size]);
  return (
    <canvas
      ref={ref}
      width={size}
      height={size}
      role="img"
      aria-label="Code QR"
      style={{ borderRadius: 'var(--radius-md)', background: '#fff' }}
    />
  );
}
