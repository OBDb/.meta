# Cookbook

## Bulk pushing changes to vehicle repos

```sh
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | grep -v ".vehicle-template" | grep -v ".github" | while read line; do pushd $line; git add .; git commit -am "Update"; git push; popd; done
```

