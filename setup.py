from setuptools import setup
from setuptools.command.install import install
from setuptools.command.develop import develop


def _install_claude_skill():
    try:
        from codebrowser.server import cmd_install_claude
        cmd_install_claude()
    except Exception:
        pass


class PostInstall(install):
    def run(self):
        install.run(self)
        _install_claude_skill()


class PostDevelop(develop):
    def run(self):
        develop.run(self)
        _install_claude_skill()


setup(
    cmdclass={
        "install": PostInstall,
        "develop": PostDevelop,
    }
)
