import {
  Button,
  Dialog,
  DialogFooter,
  Icon,
  Menu,
  MenuItem,
  Popover,
  StyledReadOnlyCodeMirror,
  Table,
} from '@dagster-io/ui-components';
import * as React from 'react';
import * as yaml from 'yaml';

import {WorkspaceRepositoryLocationNode} from './WorkspaceContext';

export const CodeLocationMenu: React.FC<{locationNode: WorkspaceRepositoryLocationNode}> = ({
  locationNode,
}) => {
  const [configIsOpen, setConfigIsOpen] = React.useState(false);
  const [libsIsOpen, setLibsIsOpen] = React.useState(false);

  let libsMenuItem = null;
  let libsDialog = null;
  if (
    locationNode.locationOrLoadError?.__typename === 'RepositoryLocation' &&
    locationNode.locationOrLoadError.dagsterLibraryVersions !== null
  ) {
    libsMenuItem = (
      <MenuItem icon="info" text="View Dagster libraries" onClick={() => setLibsIsOpen(true)} />
    );
    libsDialog = (
      <DagsterLibrariesDialog
        libraries={locationNode.locationOrLoadError.dagsterLibraryVersions}
        isOpen={libsIsOpen}
        setIsOpen={setLibsIsOpen}
      />
    );
  }

  return (
    <>
      <Popover
        position="bottom-left"
        content={
          <Menu>
            <MenuItem icon="info" text="View configuration" onClick={() => setConfigIsOpen(true)} />
            {libsMenuItem}
          </Menu>
        }
      >
        <Button icon={<Icon name="expand_more" />}></Button>
      </Popover>
      <CodeLocationConfigDialog
        metadata={locationNode.displayMetadata}
        isOpen={configIsOpen}
        setIsOpen={setConfigIsOpen}
      />
      {libsDialog}
    </>
  );
};

export const CodeLocationConfigDialog: React.FC<{
  isOpen: boolean;
  setIsOpen: (next: boolean) => void;
  metadata: WorkspaceRepositoryLocationNode['displayMetadata'];
}> = ({isOpen, setIsOpen, metadata}) => {
  return (
    <Dialog
      title="Code location configuration"
      icon="info"
      isOpen={isOpen}
      onClose={() => setIsOpen(false)}
      style={{width: '600px'}}
    >
      <CodeLocationConfig displayMetadata={metadata} />
      <DialogFooter topBorder>
        <Button onClick={() => setIsOpen(false)} intent="primary">
          Done
        </Button>
      </DialogFooter>
    </Dialog>
  );
};

export const DagsterLibrariesDialog: React.FC<{
  isOpen: boolean;
  setIsOpen: (next: boolean) => void;
  libraries: {name: string; version: string}[];
}> = ({isOpen, setIsOpen, libraries}) => {
  return (
    <Dialog
      title="Dagster library versions"
      icon="info"
      isOpen={isOpen}
      onClose={() => setIsOpen(false)}
      style={{width: '600px'}}
    >
      <Table>
        <thead>
          <tr>
            <th>Libray</th>
            <th>Version</th>
          </tr>
        </thead>
        <tbody>
          {libraries.map((library) => (
            <tr key={library.name}>
              <td>{library.name}</td>
              <td>{library.version}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <DialogFooter topBorder>
        <Button onClick={() => setIsOpen(false)} intent="primary">
          Done
        </Button>
      </DialogFooter>
    </Dialog>
  );
};

const CodeLocationConfig: React.FC<{
  displayMetadata: WorkspaceRepositoryLocationNode['displayMetadata'];
}> = ({displayMetadata}) => {
  const yamlString = React.useMemo(() => {
    const kvPairs = displayMetadata.reduce((accum, item) => {
      return {...accum, [item.key]: item.value};
    }, {});
    return yaml.stringify(kvPairs);
  }, [displayMetadata]);

  return (
    <StyledReadOnlyCodeMirror
      value={yamlString}
      options={{lineNumbers: true, mode: 'yaml'}}
      theme={['config-editor']}
    />
  );
};
