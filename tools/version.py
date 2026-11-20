
import re
import subprocess
import os
import sys

def version_str_to_tuple(version_string):
    """
    Converts a version string to a tuple of the form
    (major, minor, revision, prerelease)

    Example: "fw-v0.3.6-23" => (0, 3, 6, True)

    If version_string does not match the pattern above, this function throws an
    Exception.
    """
    regex=r'.*v([0-9]+)\.([0-9]+)\.([0-9]+)(.*)'
    if not re.match(regex, version_string):
        raise Exception()
    return (int(re.sub(regex, r"\1", version_string)),
            int(re.sub(regex, r"\2", version_string)),
            int(re.sub(regex, r"\3", version_string)),
            (re.sub(regex, r"\4", version_string) != ""))


def get_version_from_git():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    try:
        # Determine the current git commit version
        git_tag = subprocess.check_output(["git", "describe", "--always", "--tags", "--match=*fw*", "--dirty=*"],
            cwd=script_dir)
        git_tag = git_tag.decode(sys.stdout.encoding or 'ascii').rstrip('\n')

        (major, minor, revision, is_prerelease) = version_str_to_tuple(git_tag)

        # if is_prerelease:
        #     revision += 1
        return git_tag, major, minor, revision, is_prerelease

    except Exception as ex:
        print(ex)
        return "[unknown version]", 0, 0, 0, 1

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Version Dump\n')
    parser.add_argument("--output", type=argparse.FileType('w'), default='-',
                        help="C header output file")
    
    args = parser.parse_args()

    git_name, major, minor, revision, unreleased = get_version_from_git()
    print('Firmware version {}.{}.{}{} ({})'.format(
        major, minor, revision, '-dev' if unreleased else '',
        git_name))
    #args.output.write('const unsigned char fw_version = "{}"\n'.format(git_name))
    args.output.write('const unsigned char fw_version_major_ = {};\n'.format(major))
    args.output.write('const unsigned char fw_version_minor_ = {};\n'.format(minor))
    args.output.write('const unsigned char fw_version_revision_ = {};\n'.format(revision))
    args.output.write('const unsigned char fw_version_unreleased_ = {};\n'.format(1 if unreleased else 0))
