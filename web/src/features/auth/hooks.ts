// WEB-031 — appareils connectés + changement de code secret (React Query).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { changePin, listDevices, revokeDevice } from './api';

export const authQk = {
  devices: ['auth', 'devices'] as const,
};

export function useDevices() {
  return useQuery({ queryKey: authQk.devices, queryFn: listDevices });
}

export function useDeviceActions() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: authQk.devices });
  return {
    revoke: useMutation({ mutationFn: (id: string) => revokeDevice(id), onSuccess: inv }),
    changePin: useMutation({
      mutationFn: (b: { current_pin: string; new_pin: string }) => changePin(b),
    }),
  };
}
