from abc import ABC, abstractmethod

class BaseFinTechProvider(ABC):
    """
    Abstract Base Adapter interface for third-party FinTech providers.
    Ensures that internal platform APIs remain decoupled from specific vendors (e.g. Digilocker, Signzy, Cashfree, NSDL).
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns provider identifier name."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verifies connectivity to third-party provider API gateway."""
        pass


class BaseESignProvider(BaseFinTechProvider):
    @abstractmethod
    def create_esign_request(self, document_id: str, signer_info: dict) -> dict:
        """Initiates an e-sign request with third-party vendor."""
        pass

    @abstractmethod
    def get_esign_status(self, request_id: str) -> dict:
        """Fetches current e-sign status."""
        pass


class BaseKYCProvider(BaseFinTechProvider):
    @abstractmethod
    def verify_pan(self, pan_number: str, name: str) -> dict:
        """Verifies PAN details against NSDL/Income Tax database."""
        pass

    @abstractmethod
    def verify_bank_account(self, account_number: str, ifsc: str) -> dict:
        """Performs penny drop bank account verification."""
        pass
