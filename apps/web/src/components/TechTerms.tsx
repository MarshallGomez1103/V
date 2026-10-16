import { useI18n } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { Term } from './Hint'

const DEVICES: Readonly<Record<string, { label: MessageKey; def: MessageKey }>> = {
  cuda: { label: 'term.device.cuda', def: 'term.device.cuda.def' },
  cpu: { label: 'term.device.cpu', def: 'term.device.cpu.def' },
}

const PRECISIONS: Readonly<Record<string, MessageKey>> = {
  float16: 'term.precision.float16.def',
  float32: 'term.precision.float32.def',
  int8: 'term.precision.int8.def',
  int8_float16: 'term.precision.int8_float16.def',
  native: 'term.precision.native.def',
}

const PROFILES: Readonly<Record<string, { label: MessageKey; def: MessageKey }>> = {
  fast: { label: 'term.profile.fast', def: 'term.profile.fast.def' },
  quality: { label: 'term.profile.quality', def: 'term.profile.quality.def' },
}

/** Dispositivo de cómputo (GPU o CPU) con su explicación; desconocido = texto tal cual. */
export function DeviceLabel({ device, plain = false }: { device: string; plain?: boolean }) {
  const { t } = useI18n()
  const known = Object.hasOwn(DEVICES, device) ? DEVICES[device] : undefined
  return known ? (
    <Term definition={known.def} plain={plain}>
      {t(known.label)}
    </Term>
  ) : (
    <>{device}</>
  )
}

/** Precisión numérica del modelo (float16, int8…) con su explicación. */
export function PrecisionLabel({ precision, plain = false }: { precision: string; plain?: boolean }) {
  const { t } = useI18n()
  const known = Object.hasOwn(PRECISIONS, precision) ? PRECISIONS[precision] : undefined
  return known ? (
    <Term definition={known} plain={plain}>
      {precision === 'native' ? t('term.precision.native') : precision}
    </Term>
  ) : (
    <>{precision}</>
  )
}

/** Perfil de procesamiento del modelo (rápido / calidad) con su explicación. */
export function ProcessingProfileLabel({ name, plain = false }: { name: string; plain?: boolean }) {
  const { t } = useI18n()
  const known = Object.hasOwn(PROFILES, name) ? PROFILES[name] : undefined
  return known ? (
    <Term definition={known.def} plain={plain}>
      {t(known.label)}
    </Term>
  ) : (
    <>{name}</>
  )
}
