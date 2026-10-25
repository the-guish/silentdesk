REPO: ${REPO}
PR NUMBER: ${PR_NUMBER}

Read the diff with `gh pr diff` and decide whether it touches security.

It does when it changes how the code handles untrusted input, secrets, credentials, the keyring,
sign-in, network requests, file paths, processes, permissions, dependencies or CI workflows.

Answer true when unsure.
