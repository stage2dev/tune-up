// Icone de um modulo, pelo nome que o pacote do projeto informa (conjunto pequeno e generico).
import { BarChart3, Bell, Box, Calendar, FileText, Folder, Gauge, LayoutGrid, Settings, Users, Wallet, type LucideIcon } from 'lucide-react';

const ICONES: Record<string, LucideIcon> = {
  grafico: BarChart3,
  chart: BarChart3,
  alerta: Bell,
  caixa: Box,
  calendario: Calendar,
  documento: FileText,
  pasta: Folder,
  medidor: Gauge,
  config: Settings,
  pessoas: Users,
  dinheiro: Wallet,
};

export function iconeDoModulo(nome: string | undefined): LucideIcon {
  return (nome && ICONES[nome.toLowerCase()]) || LayoutGrid;
}
