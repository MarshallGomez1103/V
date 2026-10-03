import type { MessageKey } from '../i18n/messages'

export function mediaTypeLabel(mediaType: string | null): MessageKey {
  return mediaType === 'audio' ? 'media.audio' : mediaType === 'video' ? 'media.video' : 'media.unknown'
}
