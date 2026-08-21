import { AdminPasswordManager } from "@/components/admin-password-manager";
import { MissionControl } from "@/components/mission-control";

export default function AdminPage() {
  return (
    <>
      <MissionControl view="admin" />
      <AdminPasswordManager />
    </>
  );
}
