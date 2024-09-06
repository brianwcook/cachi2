from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)

import pydantic

from cachi2.core.errors import InvalidInput
from cachi2.core.models.validators import check_sane_relpath, unique
from cachi2.core.rooted_path import PathOutsideRoot, RootedPath

if TYPE_CHECKING:
    from pydantic.error_wrappers import ErrorDict

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)


def parse_user_input(to_model: Callable[[T], ModelT], input_obj: T) -> ModelT:
    """Parse user input into a model, re-raise validation errors as InvalidInput."""
    try:
        return to_model(input_obj)
    except pydantic.ValidationError as e:
        raise InvalidInput(_present_user_input_error(e)) from e


def _present_user_input_error(validation_error: pydantic.ValidationError) -> str:
    """Make a slightly nicer representation of a pydantic.ValidationError.

    Compared to pydantic's default message:
    - don't show the model name, just say "user input"
    - don't show the underlying error type (e.g. "type=value_error.const")
    """
    errors = validation_error.errors()
    n_errors = len(errors)

    def show_error(error: "ErrorDict") -> str:
        location = " -> ".join(map(str, error["loc"]))
        message = error["msg"]

        if location != "__root__":
            message = f"{location}\n  {message}"

        return message

    header = f"{n_errors} validation error{'' if n_errors == 1 else 's'} for user input"
    details = "\n".join(map(show_error, errors))
    return f"{header}\n{details}"


# Supported package managers
PackageManagerType = Literal["bundler", "gomod", "npm", "pip", "rpm", "yarn"]

Flag = Literal[
    "cgo-disable", "dev-package-managers", "force-gomod-tidy", "gomod-vendor", "gomod-vendor-check"
]


class _PackageInputBase(pydantic.BaseModel, extra="forbid"):
    """Common input attributes accepted for all package types."""

    type: PackageManagerType
    path: Path = Path(".")

    @pydantic.field_validator("path")
    def _path_is_relative(cls, path: Path) -> Path:
        return check_sane_relpath(path)


class _SSLOptions(pydantic.BaseModel, extra="forbid"):
    """SSL options model.

    Provides the 'ssl' key under 'options' for rpm package manager.

    """

    client_cert: str = None
    client_key: str = None
    ca_bundle: str = None
    ssl_verify: bool = None

    @pydantic.model_validator(mode="before")
    def _validate_ssl_options(cls, data: Any, info: pydantic.ValidationInfo) -> Optional[Dict]:

        # todo:could move valiation from _get_ssl_context to here
        return data


# class OptionsModel(pydantic.BaseModel):
#     """Optional inputs for RPM package manager."""

#     ssl: Optional[_SSLOptions] = None
#     dnf: Union[Optional[_DNFOptions]] = None

class _DNFOptions(pydantic.BaseModel, extra="forbid"):
    """DNF options model.

    DNF options can be provided via 2 'streams':
        1) global /etc/dnf/dnf.conf OR
        2) /etc/yum.repos.d/.repo files

    Config options are specified via INI format based on sections. There are 2 types of sections:
        1) global 'main' - either global repo options or DNF control-only options
            - NOTE: there must always ever be a single "main" section

        2) <repoid> sections - options tied specifically to a given defined repo

    [1] https://man7.org/linux/man-pages/man5/dnf.conf.5.html
    """

    ssl: Optional[_SSLOptions] = None

    # Don't model all known DNF options for validation purposes - it's user's responsibility!
    dnf: Dict[Union[Literal["main"], str], Dict[str, Any]] = None

    @pydantic.model_validator(mode="before")
    def _validate_dnf_options(cls, data: Any, info: pydantic.ValidationInfo) -> Optional[Dict]:
        """Fail if the user passes unexpected configuration options namespace."""

        def _raise_unexpected_type(repr_: str, *prefixes: str) -> None:
            loc = ".".join(prefixes + (repr_,))
            raise ValueError(f"Unexpected data type for '{loc}' in input JSON: expected 'dict'")

        prefixes: List[str] = ["options"]

        if not data:
            return None

        if not isinstance(data, dict):
            _raise_unexpected_type(data, *prefixes)

        extra_keys = set(data.keys() - set(cls.model_fields))
        if extra_keys:
            raise ValueError(f"Extra attributes passed in '{data}': {extra_keys}")

        if "dnf" not in data:
            # the rest of this is about validating the contents of dnf, don't run it.
            return data
        
        prefixes.append("dnf")
        options_scope = data["dnf"]
        if not isinstance(options_scope, dict):
            _raise_unexpected_type(options_scope, *prefixes)

        for repo, repo_options in options_scope.items():
            prefixes.append(repo)
            if not isinstance(repo_options, dict):
                _raise_unexpected_type(repo_options, *prefixes)

        return data


class BundlerPackageInput(_PackageInputBase):
    """Accepted input for a bundler package."""

    type: Literal["bundler"]


class GomodPackageInput(_PackageInputBase):
    """Accepted input for a gomod package."""

    type: Literal["gomod"]


class NpmPackageInput(_PackageInputBase):
    """Accepted input for a npm package."""

    type: Literal["npm"]


class PipPackageInput(_PackageInputBase):
    """Accepted input for a pip package."""

    type: Literal["pip"]
    requirements_files: Optional[list[Path]] = None
    requirements_build_files: Optional[list[Path]] = None
    allow_binary: bool = False

    @pydantic.field_validator("requirements_files", "requirements_build_files")
    def _no_explicit_none(cls, paths: Optional[list[Path]]) -> list[Path]:
        """Fail if the user explicitly passes None."""
        if paths is None:
            # Note: same error message as pydantic's default
            raise ValueError("none is not an allowed value")
        return paths

    @pydantic.field_validator("requirements_files", "requirements_build_files")
    def _requirements_file_path_is_relative(cls, paths: list[Path]) -> list[Path]:
        for p in paths:
            check_sane_relpath(p)
        return paths


class RpmPackageInput(_PackageInputBase):
    """Accepted input for RPM package manager."""

    options: Optional[_DNFOptions] = None
    type: Literal["rpm"]


class YarnPackageInput(_PackageInputBase):
    """Accepted input for a yarn package."""

    type: Literal["yarn"]


PackageInput = Annotated[
    Union[
        BundlerPackageInput,
        GomodPackageInput,
        NpmPackageInput,
        PipPackageInput,
        RpmPackageInput,
        YarnPackageInput,
    ],
    # https://pydantic-docs.helpmanual.io/usage/types/#discriminated-unions-aka-tagged-unions
    pydantic.Field(discriminator="type"),
]


class Request(pydantic.BaseModel):
    """Holds all data needed for the processing of a single request."""

    source_dir: RootedPath
    output_dir: RootedPath
    packages: list[PackageInput]
    flags: frozenset[Flag] = frozenset()

    @pydantic.field_validator("packages")
    def _unique_packages(cls, packages: list[PackageInput]) -> list[PackageInput]:
        """De-duplicate the packages to be processed."""
        return unique(packages, by=lambda pkg: (pkg.type, pkg.path))

    @pydantic.field_validator("packages")
    def _check_packages_paths(
        cls, packages: list[PackageInput], info: pydantic.ValidationInfo
    ) -> list[PackageInput]:
        """Check that package paths are existing subdirectories."""
        source_dir: RootedPath = info.data.get("source_dir", None)
        if source_dir is not None:
            for p in packages:
                try:
                    abspath = source_dir.join_within_root(p.path)
                except PathOutsideRoot:
                    raise ValueError(
                        f"package path (a symlink?) leads outside source directory: {p.path}"
                    )
                if not abspath.path.is_dir():
                    raise ValueError(
                        f"package path does not exist (or is not a directory): {p.path}"
                    )
        return packages

    @pydantic.field_validator("packages")
    def _packages_not_empty(cls, packages: list[PackageInput]) -> list[PackageInput]:
        """Check that the packages list is not empty."""
        if len(packages) == 0:
            raise ValueError("at least one package must be defined, got an empty list")
        return packages

    @property
    def bundler_packages(self) -> list[BundlerPackageInput]:
        """Get the rubygems packages specified for this request."""
        return self._packages_by_type(BundlerPackageInput)

    @property
    def gomod_packages(self) -> list[GomodPackageInput]:
        """Get the gomod packages specified for this request."""
        return self._packages_by_type(GomodPackageInput)

    @property
    def npm_packages(self) -> list[NpmPackageInput]:
        """Get the npm packages specified for this request."""
        return self._packages_by_type(NpmPackageInput)

    @property
    def pip_packages(self) -> list[PipPackageInput]:
        """Get the pip packages specified for this request."""
        return self._packages_by_type(PipPackageInput)

    @property
    def rpm_packages(self) -> list[RpmPackageInput]:
        """Get the rpm packages specified for this request."""
        return self._packages_by_type(RpmPackageInput)

    @property
    def yarn_packages(self) -> list[YarnPackageInput]:
        """Get the yarn packages specified for this request."""
        return self._packages_by_type(YarnPackageInput)

    def _packages_by_type(self, pkgtype: type[T]) -> list[T]:
        return [package for package in self.packages if isinstance(package, pkgtype)]

    # This is kept here temporarily, should be refactored
    go_mod_cache_download_part: ClassVar[Path] = Path("pkg", "mod", "cache", "download")

    # This is kept here temporarily, should be refactored
    @property
    def gomod_download_dir(self) -> RootedPath:
        """Directory where the fetched dependencies will be placed."""
        return self.output_dir.join_within_root("deps", "gomod", self.go_mod_cache_download_part)
