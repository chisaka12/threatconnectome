import {
  ArrowDropDown as ArrowDropDownIcon,
  Edit as EditIcon,
  Update as UpdateIcon,
} from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardActions,
  CardContent,
  Chip,
  ClickAwayListener,
  Collapse,
  Divider,
  Grow,
  IconButton,
  List,
  MenuList,
  MenuItem,
  Switch,
  Typography,
  Paper,
  Popper,
} from "@mui/material";
import { grey } from "@mui/material/colors";
import PropTypes from "prop-types";
import React, { useEffect, useState, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useParams } from "react-router-dom";

import {
  getDependencies,
  getPTeamTopicActions,
  getTicketsRelatedToServiceTopicTag,
} from "../slices/pteam";
import { getTopic } from "../slices/topics";
import { dateTimeFormat } from "../utils/func";
import { isComparable, parseVulnerableVersions, versionMatch } from "../utils/versions";

import { ActionItem } from "./ActionItem";
import { PTeamEditAction } from "./PTeamEditAction";
import { ReportCompletedActions } from "./ReportCompletedActions";
import { TopicModal } from "./TopicModal";
import { TopicTicketAccordion } from "./TopicTicketAccordion";
import { UUIDTypography } from "./UUIDTypography";

export function TopicCard(props) {
  const { pteamId, topicId, currentTagId, serviceId, references } = props;
  const { tagId } = useParams();

  const [detailOpen, setDetailOpen] = useState(false);
  const [topicModalOpen, setTopicModalOpen] = useState(false);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [actionFilter, setActionFilter] = useState(true);
  const [pteamActionModalOpen, setPteamActionModalOpen] = useState(false);

  const anchorRef = useRef(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [openActionMenu, setOpenActionMenu] = useState(false);
  const [actionColor, setActionColor] = useState("primary");

  const members = useSelector((state) => state.pteam.members); // dispatched by Tag.jsx
  const serviceDependencies = useSelector((state) => state.pteam.serviceDependencies);
  const ticketsDict = useSelector((state) => state.pteam.tickets);
  const pteamTopicActionsDict = useSelector((state) => state.pteam.topicActions);
  const topics = useSelector((state) => state.topics.topics);
  const allTags = useSelector((state) => state.tags.allTags); // dispatched by parent

  const dependencies = serviceDependencies[serviceId];
  const topic = topics[topicId];
  const tickets = ticketsDict[serviceId]?.[tagId]?.[topicId];
  const pteamTopicActions = pteamTopicActionsDict[topicId];

  const dispatch = useDispatch();

  useEffect(() => {
    if (!pteamId || !serviceId || !topicId || !tagId) return;
    if (tickets === undefined) {
      dispatch(
        getTicketsRelatedToServiceTopicTag({
          pteamId: pteamId,
          serviceId: serviceId,
          topicId: topicId,
          tagId: tagId,
        }),
      );
    }
  }, [dispatch, pteamId, serviceId, topicId, tagId, tickets]);

  useEffect(() => {
    if (!pteamId || !serviceId) return;
    if (dependencies === undefined) {
      dispatch(getDependencies({ pteamId: pteamId, serviceId: serviceId }));
    }
  }, [dispatch, pteamId, serviceId, dependencies]);

  useEffect(() => {
    if (!topicId) return;
    if (topic === undefined) {
      dispatch(getTopic(topicId));
    }
  }, [dispatch, topicId, topic]);

  useEffect(() => {
    if (!pteamId || !topicId) return;
    if (pteamTopicActions === undefined) {
      dispatch(getPTeamTopicActions({ pteamId: pteamId, topicId: topicId }));
    }
  }, [dispatch, pteamId, topicId, pteamTopicActions]);

  const handleActionMenuClose = () => {};

  const handleDetailOpen = () => setDetailOpen(!detailOpen);

  if (!pteamId || !serviceId || !members || !topic || !tagId || !tickets || !allTags) {
    return <>Now Loading...</>;
  }

  const isSolved = !tickets.find(
    (ticket) => ticket.current_ticket_status?.topic_status !== "completed",
  );
  const currentTagDict = allTags.find((tag) => tag.tag_id === tagId);

  const takenActionLogs = isSolved // FIXME: WORKAROUND, just list taken actions of each tickets
    ? tickets.reduce((ret, ticket) => [...ret, ...ticket.current_ticket_status.action_logs], [])
    : [];

  // oops, ext.tags are list of tag NAME. (because generated by script without TC)
  const isRelatedAction = (action, tagName) =>
    (!action.ext?.tags?.length > 0 || action.ext.tags.includes(tagName)) &&
    (!action.ext?.vulnerable_versions?.[tagName]?.length > 0 ||
      parseVulnerableVersions(action.ext.vulnerable_versions[tagName]).some(
        (actionVersion) =>
          !references?.length > 0 ||
          references?.some((ref) =>
            versionMatch(
              ref.version,
              actionVersion.ge,
              actionVersion.gt,
              actionVersion.le,
              actionVersion.lt,
              actionVersion.eq,
              true,
            ),
          ),
      ));
  const topicActions = actionFilter
    ? pteamTopicActions?.filter(
        (action) =>
          isRelatedAction(action, currentTagDict.tag_name) ||
          isRelatedAction(action, currentTagDict.parent_name),
      )
    : pteamTopicActions ?? [];

  const options = ["Report completed actions", "Add other actions"];

  const handleClick = () => {
    if (selectedIndex === 0) {
      setActionModalOpen(true);
    }
    if (selectedIndex === 1) {
      setPteamActionModalOpen(true);
    }
  };

  const handleMenuItemClick = (index) => {
    setSelectedIndex(index);
    setOpenActionMenu(false);

    if (index === 0) {
      setActionColor("primary");
    }
    if (index === 1) {
      setActionColor("success");
    }
  };

  const handleToggle = () => {
    setOpenActionMenu((prevOpen) => !prevOpen);
  };

  const handleClose = (event) => {
    if (anchorRef.current && anchorRef.current.contains(event.target)) {
      return;
    }
    setOpenActionMenu(false);
  };

  const checkCompalable = () => {
    const tagNames = [currentTagDict.tag_name, currentTagDict.parent_name];
    return tagNames.every((tagName) => {
      return pteamTopicActions?.every((action) => {
        return parseVulnerableVersions(action.ext?.vulnerable_versions?.[tagName]).every(
          (actionVersion) => {
            return references?.every((ref) => {
              return (
                (actionVersion.ge === undefined || isComparable(ref.version, actionVersion.ge)) &&
                (actionVersion.gt === undefined || isComparable(ref.version, actionVersion.gt)) &&
                (actionVersion.le === undefined || isComparable(ref.version, actionVersion.le)) &&
                (actionVersion.lt === undefined || isComparable(ref.version, actionVersion.lt)) &&
                (actionVersion.eq === undefined || isComparable(ref.version, actionVersion.eq))
              );
            });
          },
        );
      });
    });
  };

  return (
    <Card variant="outlined" sx={{ marginTop: "8px", marginBottom: "20px", width: "100%" }}>
      <Box
        display="flex"
        flexDirection="row"
        justifyContent="space-between"
        alignItems="flex-start"
      >
        <Box display="flex" flexDirection="row" alignItems="flex-start" m={2} mb={1}>
          <Box display="flex" flexDirection="column" mr={1}>
            <Typography variant="h5" fontWeight={900}>
              {topic?.title}
            </Typography>
            <UUIDTypography>{topic?.topic_id}</UUIDTypography>
            <Box alignItems="center" display="flex" flexDirection="row" sx={{ color: grey[600] }}>
              <UpdateIcon fontSize="small" />
              <Typography ml={0.5} variant="caption">
                {dateTimeFormat(topic?.updated_at)}
              </Typography>
            </Box>
          </Box>
        </Box>
        <Box mt={3} mr={2} display="flex" flexDirection="row">
          {references?.length === 0 && (
            <Alert severity="warning" ml={2}>
              {"It cannot be auto-closed, because reference is not set."}
            </Alert>
          )}
          {checkCompalable() === false && (
            <Alert severity="warning" ml={2}>
              {"It cannot be auto-closed, so please input it manually."}
            </Alert>
          )}
          <IconButton onClick={() => setTopicModalOpen(true)}>
            <EditIcon />
          </IconButton>
        </Box>
        <TopicModal
          open={topicModalOpen}
          onSetOpen={setTopicModalOpen}
          presetTopicId={topicId}
          presetTagId={currentTagId}
          presetParentTagId={currentTagDict.parent_id}
          presetActions={pteamTopicActions}
          serviceId={serviceId}
        />
      </Box>
      <Divider />
      <Box display="flex" sx={{ height: "350px" }}>
        <Box flexGrow={1} display="flex" flexDirection="column" justifyContent="space-between">
          <CardContent>
            {!isSolved ? (
              topicActions && (
                <>
                  <Box alignItems="center" display="flex" flexDirection="row" mb={1}>
                    <Typography mr={2} sx={{ fontWeight: 900 }}>
                      Recommended action
                      {topicActions.filter((action) => action.recommended).length > 1 ? "s" : ""}
                    </Typography>
                    <Chip
                      size="small"
                      label={topicActions.filter((action) => action.recommended).length}
                      sx={{ backgroundColor: grey[300], fontWeight: 900 }}
                    />
                    <Box display="flex" flexGrow={1} flexDirection="row" />
                    <Switch
                      checked={actionFilter}
                      onChange={() => setActionFilter(!actionFilter)}
                      size="small"
                      color="success"
                    />
                    <Typography>Action filter</Typography>
                  </Box>
                  <List
                    sx={{
                      width: "100%",
                      position: "relative",
                      overflow: "auto",
                      maxHeight: 200,
                    }}
                  >
                    {topicActions
                      .filter((action) => action.recommended)
                      .map((action) => (
                        <ActionItem
                          key={action.action_id}
                          action={action.action}
                          actionId={action.action_id}
                          actionType={action.action_type}
                          createdAt={action.created_at}
                          recommended={action.recommended}
                          ext={action.ext}
                          focusTags={
                            actionFilter
                              ? null
                              : [currentTagDict.tag_name, currentTagDict.parent_name]
                          }
                        />
                      ))}
                  </List>
                </>
              )
            ) : (
              <>
                <Box alignItems="center" display="flex" flexDirection="row" mb={2}>
                  <Typography mr={2} sx={{ fontWeight: 900 }}>
                    Taken Action
                    {takenActionLogs.length > 1 ? "s" : ""}
                  </Typography>
                  <Chip
                    size="small"
                    label={takenActionLogs.length}
                    sx={{ backgroundColor: grey[300], fontWeight: 900 }}
                  />
                  <Box display="flex" flexGrow={1} flexDirection="row" />
                  <Switch
                    checked={actionFilter}
                    onChange={() => setActionFilter(!actionFilter)}
                    size="small"
                  />
                  <Typography>Action filter</Typography>
                </Box>
                <List
                  sx={{
                    width: "100%",
                    position: "relative",
                    overflow: "auto",
                    maxHeight: 200,
                  }}
                >
                  {takenActionLogs.map((log) => (
                    <ActionItem
                      key={log.logging_id}
                      action={log.action}
                      actionId={log.action_id}
                      actionType={log.action_type}
                      recommended={log.recommended}
                    />
                  ))}
                </List>
              </>
            )}
            <Collapse in={detailOpen}>
              {(() => {
                const otherActions = topicActions?.filter((action) =>
                  isSolved
                    ? !takenActionLogs?.find((log) => log.action_id === action.action_id)
                    : !action.recommended,
                );
                return otherActions?.length >= 1 ? (
                  <>
                    <Box alignItems="baseline" display="flex" flexDirection="columns" mt={4}>
                      <Typography mr={2} sx={{ fontWeight: 900 }}>
                        Other action{otherActions.length > 1 ? "s" : ""}
                      </Typography>
                      <Chip
                        size="small"
                        label={otherActions.length}
                        sx={{ backgroundColor: grey[300], fontWeight: 900 }}
                      />
                    </Box>
                    <List
                      sx={{
                        width: "100%",
                        position: "relative",
                        overflow: "auto",
                        maxHeight: 200,
                      }}
                    >
                      {otherActions.map((action) => (
                        <ActionItem
                          key={action.action_id}
                          action={action.action}
                          actionId={action.action_id}
                          actionType={action.action_type}
                          createdAt={action.created_at}
                          recommended={action.recommended}
                          ext={action.ext}
                          focusTags={
                            actionFilter
                              ? null
                              : [currentTagDict.tag_name, currentTagDict.parent_name]
                          }
                        />
                      ))}
                    </List>
                  </>
                ) : (
                  <></>
                );
              })()}
              {topic.misp_tags && topic.misp_tags.length > 0 && (
                <>
                  <Typography sx={{ fontWeight: 900 }} mt={3} mb={2}>
                    MISP tags
                  </Typography>
                  <Box mb={5}>
                    {topic.misp_tags.map((mispTag) => (
                      <Chip
                        key={mispTag.tag_id}
                        label={mispTag.tag_name}
                        sx={{ mr: 1, borderRadius: "3px" }}
                        size="small"
                      />
                    ))}
                  </Box>
                </>
              )}
              {topic.abstract && (
                <>
                  <Typography sx={{ fontWeight: 900 }} mb={2}>
                    Detail
                  </Typography>
                  <Typography variant="body">{topic.abstract}</Typography>
                </>
              )}
            </Collapse>
          </CardContent>
          <CardActions sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
            <Button
              color="primary"
              onClick={handleDetailOpen}
              size="small"
              sx={{ marginRight: "auto", textTransform: "none" }}
            >
              {detailOpen ? "Hide" : "Show"} Details
            </Button>
            {!isSolved && topicActions && (
              <>
                <ButtonGroup
                  variant="contained"
                  ref={anchorRef}
                  aria-label="split button"
                  color={actionColor}
                >
                  <Button onClick={handleClick} sx={{ textTransform: "none" }}>
                    {options[selectedIndex]}
                  </Button>
                  <Button
                    size="small"
                    aria-controls={openActionMenu ? "split-button-menu" : undefined}
                    aria-expanded={openActionMenu ? "true" : undefined}
                    aria-haspopup="menu"
                    onClick={handleToggle}
                    // sx={{ textTransform: "none", backgroundColor: actionColor }}
                  >
                    <ArrowDropDownIcon />
                  </Button>
                </ButtonGroup>
                <Popper
                  sx={{
                    zIndex: 1,
                  }}
                  open={openActionMenu}
                  anchorEl={anchorRef.current}
                  role={undefined}
                  transition
                >
                  {({ TransitionProps }) => (
                    <Grow {...TransitionProps}>
                      <Paper>
                        <ClickAwayListener onClickAway={handleClose}>
                          <MenuList id="split-button-menu" autoFocusItem>
                            {options.map((option, index) => (
                              <MenuItem
                                key={option}
                                selected={index === selectedIndex}
                                onClick={() => handleMenuItemClick(index)}
                              >
                                {option}
                              </MenuItem>
                            ))}
                          </MenuList>
                          z
                        </ClickAwayListener>
                      </Paper>
                    </Grow>
                  )}
                </Popper>
              </>
            )}
          </CardActions>
          <ReportCompletedActions
            onConfirm={handleActionMenuClose}
            onSetShow={setActionModalOpen}
            show={actionModalOpen}
            topicId={topicId}
            topicActions={topicActions}
            serviceId={serviceId}
          />
          <PTeamEditAction
            open={pteamActionModalOpen}
            onSetOpen={setPteamActionModalOpen}
            presetTopicId={topicId}
            presetTagId={currentTagId}
            presetParentTagId={currentTagDict.parent_id}
            presetActions={pteamTopicActions}
            currentTagDict={currentTagDict}
            references={references}
            serviceId={serviceId}
          />
        </Box>
        <Divider flexItem={true} orientation="vertical" />
        <Box
          sx={{
            overflowY: "auto",
            minWidth: "320px",
            maxWidth: "350px",
          }}
        >
          {tickets.map((ticket, index) => (
            <TopicTicketAccordion
              key={ticket.ticket_id}
              pteamId={pteamId}
              dependency={dependencies.find(
                (dependency) => dependency.dependency_id === ticket.threat.dependency_id,
              )}
              topicId={topicId}
              ticket={ticket}
              members={members}
              defaultExpanded={index === 0}
            />
          ))}
        </Box>
      </Box>
    </Card>
  );
}

TopicCard.propTypes = {
  pteamId: PropTypes.string.isRequired,
  topicId: PropTypes.string.isRequired,
  currentTagId: PropTypes.string.isRequired,
  serviceId: PropTypes.string.isRequired,
  references: PropTypes.array.isRequired,
};
