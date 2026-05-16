from resource_server.auth.role_mapping import identity_role_mapper


class TestIdentityRoleMapper:
    def test_returns_admin_unchanged(self) -> None:
        assert identity_role_mapper("admin") == "admin"

    def test_returns_reader_unchanged(self) -> None:
        assert identity_role_mapper("reader") == "reader"

    def test_returns_writer_unchanged(self) -> None:
        assert identity_role_mapper("writer") == "writer"

    def test_returns_arbitrary_string_unchanged(self) -> None:
        assert identity_role_mapper("custom-role") == "custom-role"
