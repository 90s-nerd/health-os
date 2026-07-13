import {
  Activity,
  Bed,
  CheckCircle2,
  ClipboardCheck,
  Coffee,
  CupSoda,
  Droplets,
  Egg,
  Footprints,
  GlassWater,
  Moon,
  Salad,
  Scale,
  ShoppingBasket,
  Smartphone,
  Sunrise,
  Utensils,
  Bike,
  Circle,
} from "lucide-react";
const icons: Record<string, typeof Circle> = {
  activity: Activity,
  bed: Bed,
  "clipboard-check": ClipboardCheck,
  coffee: Coffee,
  "cup-soda": CupSoda,
  droplets: Droplets,
  egg: Egg,
  footprints: Footprints,
  "glass-water": GlassWater,
  moon: Moon,
  salad: Salad,
  scale: Scale,
  "shopping-basket": ShoppingBasket,
  "smartphone-off": Smartphone,
  sunrise: Sunrise,
  utensils: Utensils,
  bike: Bike,
  check: CheckCircle2,
};
export function HabitIcon({
  name,
  size = 20,
}: {
  name: string;
  size?: number;
}) {
  const Icon = icons[name] || Circle;
  return <Icon size={size} strokeWidth={1.8} />;
}
