# Cookbook

## Bulk cloning all vehicle repos

```
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | while read line; do git clone git@github.com:ElectricSidecar/$line.git; done
```

## Update all repos

```
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | while read line; do pushd $line; git fetch; git rebase origin/main; popd; done
```

## Bulk updating signalset version


```
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | grep -v ".vehicle-template" | grep -v "ElectricSidecar" | grep -v "^.github" | grep -v "^meta" | while read line; do pushd $line; cp ../.vehicle-template/.github/workflows/json-yaml-validate.yml .github/workflows/json-yaml-validate.yml; popd; done
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | grep -v ".vehicle-template" | grep -v "ElectricSidecar" | grep -v "^.github" | grep -v "^meta" | while read line; do pushd $line; cp -r ../.vehicle-template/schema/ schema; popd; done
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | grep -v ".vehicle-template" | grep -v "ElectricSidecar" | grep -v "^.github" | grep -v "^meta" | while read line; do pushd $line; git add .; git commit -a -m "Add schema"; git push; popd; done
```

## Bulk pushing changes to vehicle repos

```sh
gh repo list electricsidecar --limit 100 | grep "ElectricSidecar/" | cut -f1 | cut -d'/' -f2 | grep -v ".vehicle-template" | grep -v ".github" | while read line; do pushd $line; git add .; git commit -am "Update"; git push; popd; done
```

