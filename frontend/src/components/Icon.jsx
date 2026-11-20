import { House, GraduationCap, UserRound, SlidersHorizontal, Heart, ClipboardList, FileText, Building2, Radar, Pencil, LogOut, Search, FilterX, Plus, Save, X, Trash2, Eye, ArrowLeft, Download, ExternalLink, ListChecks, RefreshCw, ChevronLeft, ChevronRight, CircleCheck, CircleX, CircleHelp, TriangleAlert, Info, LoaderCircle, LogIn, UserPlus, Pause, Send, Bell, Mail } from 'lucide-react'

const icons = {
  home: House, explore: GraduationCap, profile: UserRound, preferences: SlidersHorizontal,
  favorite: Heart, offers: ClipboardList, document: FileText, institutions: Building2, crawling: Radar,
  edit: Pencil, logout: LogOut, search: Search, clear: FilterX, add: Plus, save: Save,
  cancel: X, delete: Trash2, detail: Eye, back: ArrowLeft, download: Download,
  external: ExternalLink, compare: ListChecks, refresh: RefreshCw, previous: ChevronLeft,
  next: ChevronRight, success: CircleCheck, failure: CircleX, pending: CircleHelp,
  warning: TriangleAlert, info: Info, loading: LoaderCircle, login: LogIn, register: UserPlus,
  pause: Pause, publish: Send, notifications: Bell, mail: Mail,
}

// Iconos decorativos: el texto visible conserva el significado y nombre accesible.
export default function Icon({ name }) {
  const Glyph = icons[name]
  return Glyph ? <Glyph aria-hidden="true" focusable="false" size={20} strokeWidth={1.8} className={`ui-icon${name === 'loading' ? ' ui-icon-loading' : ''}`} /> : null
}
